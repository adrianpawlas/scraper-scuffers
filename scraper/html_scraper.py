"""
HTML scraper for fashion websites.
Handles product page scraping and parsing.
"""

import logging
import re
import time
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class HTMLScraper:
    def __init__(self, user_agent: str = None, delay: float = 1.0):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.delay = delay
        logger.info(f"HTML Scraper initialized with delay: {delay}s")

    def scrape_category_page(self, url: str, selectors: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Scrape a category page for product listings.

        Args:
            url: Category page URL
            selectors: CSS selectors for extracting product data

        Returns:
            List of product dictionaries with basic info
        """
        logger.info(f"Scraping category page: {url}")

        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'lxml')

            # Method 1: Try to find product containers first
            product_containers = soup.select(selectors.get('products', '.product-item'))
            products = []

            if product_containers:
                logger.info(f"Found {len(product_containers)} product containers")
                for container in product_containers:
                    product_data = self._extract_product_from_listing(container, url, selectors)
                    if product_data:
                        products.append(product_data)
            else:
                # Method 2: If no containers found, look for product links directly
                logger.info("No product containers found, trying direct link extraction")
                product_links = soup.select(selectors.get('product_url', "a[href*='/products/']"))

                # Filter out duplicates and gift cards
                seen_urls = set()
                unique_links = []
                for link in product_links:
                    href = link.get('href')
                    if href and '/products/' in href:
                        # Skip gift cards and other non-product items
                        if any(skip in href.lower() for skip in ['giftcard', 'gift-card', 'card']):
                            continue
                        if href not in seen_urls:
                            seen_urls.add(href)
                            unique_links.append(link)

                logger.info(f"Found {len(unique_links)} unique product links")

                for link in unique_links[:50]:  # Limit to first 50 to avoid overwhelming
                    product_data = self._extract_product_from_link(link, url, selectors)
                    if product_data:
                        products.append(product_data)

            logger.info(f"Extracted {len(products)} products from category page")
            return products

        except Exception as e:
            logger.error(f"Failed to scrape category page {url}: {e}")
            return []

    def scrape_product_page(self, url: str, selectors: Dict[str, str], config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Scrape individual product page for detailed information.

        Args:
            url: Product page URL
            selectors: CSS selectors for extracting data
            config: Site configuration

        Returns:
            Complete product dictionary or None if failed
        """
        logger.debug(f"Scraping product page: {url}")

        try:
            # Respect delay between requests
            time.sleep(self.delay)

            # Try with retry logic
            max_retries = 3
            response = None
            for attempt in range(max_retries):
                try:
                    response = self.session.get(url, timeout=15)  # Increased timeout
                    response.raise_for_status()
                    break
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 * (attempt + 1))  # Exponential backoff
                    else:
                        logger.error(f"All attempts failed for {url}")
                        return None

            soup = BeautifulSoup(response.content, 'lxml')

            product_data = {
                'source': config.get('source'),
                'merchant_name': config.get('merchant_name'),
                'brand': config.get('brand'),
                'second_hand': config.get('second_hand', False),
                'country': config.get('country', 'eu'),
                'currency': config.get('currency', 'EUR'),
                'product_url': url
            }

            # Extract external_id from URL
            external_id = self._extract_external_id(url)
            if external_id:
                product_data['external_id'] = external_id
            else:
                # Fallback: use the product URL path
                parsed_url = urlparse(url)
                product_data['external_id'] = parsed_url.path.strip('/').replace('/', '-')

            # Extract title - try multiple selectors for product pages
            title = None

            # Try specific product title selectors first
            title_selectors = [
                'h1.product-title',
                '.product-title',
                'h1',
                '[class*="title"]',
                '.title'
            ]

            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    candidate_title = title_elem.get_text(strip=True)
                    # Skip if it's a generic page title or collection title
                    if candidate_title and len(candidate_title) > 3 and not any(skip in candidate_title.lower() for skip in ['all products', 'collection', 'scuffers', 'size guide']):
                        title = candidate_title
                        break

            # Fallback: try to extract from meta tags
            if not title:
                meta_title = soup.find('meta', attrs={'property': 'og:title'})
                if meta_title and meta_title.get('content'):
                    title = meta_title.get('content').strip()

            # Last fallback: extract from URL
            if not title and 'product_url' in product_data:
                url_parts = product_data['product_url'].split('/')
                if 'products' in url_parts:
                    product_index = url_parts.index('products')
                    if product_index + 1 < len(url_parts):
                        title = url_parts[product_index + 1].replace('-', ' ').title()

            if title:
                product_data['title'] = title

            # Extract price - try multiple approaches
            price = None

            # Try direct price selectors
            price_selectors = [
                '.price',
                '[data-price]',
                '.product-price',
                '[class*="price"]',
                '.money'
            ]

            for selector in price_selectors:
                price_elem = soup.select_one(selector)
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    # Skip if this looks like filter/navigation text
                    if any(skip_word in price_text.lower() for skip_word in [
                        'price', 'low to high', 'high to low', 'filter', 'sort',
                        'new arrivals', 'best sellers', 'on sale'
                    ]):
                        continue

                    # Look for price pattern in the text
                    import re
                    price_match = re.search(r'(\d+[,.]\d+)', price_text)
                    if price_match:
                        price = price_match.group(1)
                        break

            # Try to find price in script tags or other elements
            if not price:
                price = self._find_price_in_page(soup)

            # Try meta tags
            if not price:
                meta_price = soup.find('meta', attrs={'property': 'product:price:amount'})
                if meta_price and meta_price.get('content'):
                    price = meta_price.get('content')

            # Try JSON-LD structured data
            if not price:
                json_ld_scripts = soup.find_all('script', type='application/ld+json')
                for script in json_ld_scripts:
                    try:
                        import json
                        data = json.loads(script.string)
                        if isinstance(data, dict) and 'offers' in data:
                            offers = data['offers']
                            if isinstance(offers, list) and offers:
                                offer = offers[0]
                            elif isinstance(offers, dict):
                                offer = offers
                            else:
                                continue

                            if 'price' in offer:
                                price = str(offer['price'])
                                break
                    except (json.JSONDecodeError, KeyError):
                        continue

            if price:
                product_data['price'] = price

            # Extract image URL - prioritize actual product images over placeholders
            img_url = None

            # First try to find CDN images that are likely product photos
            cdn_images = soup.select('img[src*="cdn"], img[src^="//"]')
            for img in cdn_images:
                src = img.get('src', '')
                alt = img.get('alt', '').lower()
                classes = ' '.join(img.get('class', [])).lower()

                # Skip logos, icons, and placeholder images
                if any(skip in src.lower() for skip in ['logo', 'icon', 'social', 'flag', 'placeholder']):
                    continue
                if any(skip in alt for skip in ['logo', 'icon', 'flag', 'scuffers']):
                    continue
                if 'logo' in classes or 'icon' in classes:
                    continue

                # Look for images that are likely product photos (contain product name or have reasonable size)
                if any(keyword in src.lower() for keyword in ['jpg', 'jpeg', 'png']) and len(src) > 50:
                    img_url = src
                    break

            # Fallback to the selector if we didn't find a good image
            if not img_url:
                img_elem = soup.select_one(selectors.get('image_url', 'img[src*="cdn.shopify.com"]'))
                if img_elem:
                    img_url = img_elem.get('src')

            if img_url:
                # Convert relative URLs to absolute
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                elif img_url.startswith('/'):
                    base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
                    img_url = urljoin(base_url, img_url)
                product_data['image_url'] = img_url

            # Extract sizes
            size_elements = soup.select(selectors.get('sizes', '.size-option, [data-size]'))
            if size_elements:
                sizes = [elem.get_text(strip=True) for elem in size_elements if elem.get_text(strip=True)]
                if sizes:
                    product_data['size'] = ', '.join(sizes)

            # Try to determine gender
            gender = self._determine_gender(soup, selectors, url)
            if gender:
                product_data['gender'] = gender

            # Extract description
            desc_elem = soup.select_one('.product-description, .description, [data-description]')
            if desc_elem:
                product_data['description'] = desc_elem.get_text(strip=True)

            logger.debug(f"Extracted product data: {product_data}")
            return product_data

        except Exception as e:
            logger.error(f"Failed to scrape product page {url}: {e}")
            return None

    def _extract_product_from_listing(self, container, base_url: str, selectors: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Extract basic product info from a listing container.

        Args:
            container: BeautifulSoup element containing product listing
            base_url: Base URL for relative links
            selectors: CSS selectors

        Returns:
            Basic product dictionary or None
        """
        try:
            # Extract product URL
            link_elem = container.select_one(selectors.get('product_url', 'a'))
            if not link_elem:
                return None

            product_url = link_elem.get('href')
            if product_url:
                if product_url.startswith('/'):
                    base_parsed = urlparse(base_url)
                    product_url = f"{base_parsed.scheme}://{base_parsed.netloc}{product_url}"
            else:
                return None

            product_data = {
                'product_url': product_url,
                'external_id': self._extract_external_id(product_url) or product_url.split('/')[-1]
            }

            # Extract title
            title_elem = container.select_one(selectors.get('title', '.title, h3'))
            if title_elem:
                product_data['title'] = title_elem.get_text(strip=True)

            # Extract price
            price_elem = container.select_one(selectors.get('price', '.price'))
            if price_elem:
                product_data['price'] = price_elem.get_text(strip=True)

            # Extract image URL
            img_elem = container.select_one(selectors.get('image_url', 'img'))
            if img_elem:
                img_url = img_elem.get('src') or img_elem.get('data-src')
                if img_url:
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        base_parsed = urlparse(base_url)
                        img_url = f"{base_parsed.scheme}://{base_parsed.netloc}{img_url}"
                    product_data['image_url'] = img_url

            return product_data

        except Exception as e:
            logger.error(f"Failed to extract product from listing: {e}")
            return None

    def _extract_product_from_link(self, link_elem, base_url: str, selectors: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Extract basic product info from a product link element.

        Args:
            link_elem: BeautifulSoup link element
            base_url: Base URL for relative links
            selectors: CSS selectors

        Returns:
            Basic product dictionary or None
        """
        try:
            product_url = link_elem.get('href')
            if not product_url:
                return None

            if product_url.startswith('/'):
                base_parsed = urlparse(base_url)
                product_url = f"{base_parsed.scheme}://{base_parsed.netloc}{product_url}"

            product_data = {
                'product_url': product_url,
                'external_id': self._extract_external_id(product_url) or product_url.split('/')[-1]
            }

            # Try to extract title from link text or nearby elements
            link_text = link_elem.get_text(strip=True)
            if link_text and len(link_text) > 10:  # Likely a product title
                # Clean up the text (remove size info, etc.)
                title = link_text.split(' EUR')[0]  # Remove price part
                title = title.split(' +')[0]  # Remove stock indicator
                # Remove size indicators
                import re
                title = re.sub(r'\b(XS|S|M|L|XL|XXL|\d+)\b', '', title).strip()
                if title:
                    product_data['title'] = title

            # Look for price in the parent container or siblings
            parent = link_elem.parent
            if parent:
                # Look for price patterns in parent text
                parent_text = parent.get_text()
                import re
                price_match = re.search(r'(\d+,\d+)\s*EUR', parent_text)
                if price_match:
                    product_data['price'] = price_match.group(1) + ' EUR'

                # Look for image in parent container
                img_elem = parent.select_one('img')
                if img_elem:
                    img_url = img_elem.get('src') or img_elem.get('data-src')
                    if img_url:
                        if img_url.startswith('//'):
                            img_url = 'https:' + img_url
                        elif img_url.startswith('/'):
                            base_parsed = urlparse(base_url)
                            img_url = f"{base_parsed.scheme}://{base_parsed.netloc}{img_url}"
                        product_data['image_url'] = img_url

            return product_data

        except Exception as e:
            logger.error(f"Failed to extract product from link: {e}")
            return None

    def _extract_external_id(self, url: str) -> Optional[str]:
        """
        Extract external ID from product URL.

        Args:
            url: Product URL

        Returns:
            External ID or None
        """
        # For Shopify stores, the product ID is often in the URL path
        # e.g., /products/new-navy-raw-jacket -> new-navy-raw-jacket
        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')

        if 'products' in path_parts:
            products_index = path_parts.index('products')
            if products_index + 1 < len(path_parts):
                product_handle = path_parts[products_index + 1]
                # Try to extract numeric ID if present
                match = re.search(r'(\d+)', product_handle)
                if match:
                    return match.group(1)
                else:
                    return product_handle

        return None

    def _find_price_in_page(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Find price in various places on the page.

        Args:
            soup: BeautifulSoup object

        Returns:
            Price string or None
        """
        # Look in script tags for JSON data
        scripts = soup.find_all('script', string=re.compile(r'price|Price'))
        for script in scripts:
            match = re.search(r'"price":\s*"([^"]+)"', script.string or '')
            if match:
                return match.group(1)

        # Look for data attributes
        price_elements = soup.find_all(attrs={'data-price': True})
        if price_elements:
            return price_elements[0].get('data-price')

        return None

    def _determine_gender(self, soup: BeautifulSoup, selectors: Dict[str, str], url: str) -> Optional[str]:
        """
        Determine product gender from page content.

        Args:
            soup: BeautifulSoup object
            selectors: CSS selectors
            url: Product URL

        Returns:
            'men', 'women', or None
        """
        # Check URL for gender indicators
        url_lower = url.lower()
        if 'women' in url_lower or 'woman' in url_lower or 'female' in url_lower:
            return 'women'
        elif 'men' in url_lower or 'man' in url_lower or 'male' in url_lower:
            return 'men'

        # Check meta description for gender indicators (e.g., "Model (man) wearing...")
        meta_desc = soup.select_one('meta[name="description"]')
        if meta_desc:
            desc_content = meta_desc.get('content', '').lower()
            if '(man)' in desc_content or '(male)' in desc_content or 'man wearing' in desc_content:
                return 'men'
            elif '(woman)' in desc_content or '(female)' in desc_content or 'woman wearing' in desc_content:
                return 'women'

        # Check breadcrumbs for gender context
        breadcrumbs = soup.select('.breadcrumb, .breadcrumbs, [class*="breadcrumb"]')
        for crumb in breadcrumbs:
            crumb_text = crumb.get_text().lower()
            if 'women' in crumb_text or 'woman' in crumb_text or 'female' in crumb_text:
                return 'women'
            elif 'men' in crumb_text or 'man' in crumb_text or 'male' in crumb_text:
                return 'men'

        # Check page title
        title_elem = soup.select_one('title')
        if title_elem:
            title_text = title_elem.get_text().lower()
            if 'women' in title_text or 'woman' in title_text:
                return 'women'
            elif 'men' in title_text or 'man' in title_text:
                return 'men'

        # Check specific selectors
        gender_elem = soup.select_one(selectors.get('gender', '.gender, .category'))
        if gender_elem:
            gender_text = gender_elem.get_text().lower()
            if 'women' in gender_text or 'woman' in gender_text:
                return 'women'
            elif 'men' in gender_text or 'man' in gender_text:
                return 'men'

        # Check product description for gender indicators
        desc_elem = soup.select_one('.product-description, .description, [class*="description"]')
        if desc_elem:
            desc_text = desc_elem.get_text().lower()
            if any(term in desc_text for term in ['men\'s', 'man\'s', 'male', 'unisex']):
                if 'unisex' in desc_text:
                    return None  # Could be either
                elif any(term in desc_text for term in ['men\'s', 'man\'s', 'male']):
                    return 'men'

        # Default to None - will be determined by collection context
        return None
