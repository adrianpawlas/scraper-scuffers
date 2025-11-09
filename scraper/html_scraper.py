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

            # Find all product containers
            product_containers = soup.select(selectors.get('products', '.product-item'))

            products = []
            for container in product_containers:
                product_data = self._extract_product_from_listing(container, url, selectors)
                if product_data:
                    products.append(product_data)

            logger.info(f"Found {len(products)} products on category page")
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
        logger.info(f"Scraping product page: {url}")

        try:
            # Respect delay between requests
            time.sleep(self.delay)

            response = self.session.get(url, timeout=10)
            response.raise_for_status()

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

            # Extract title
            title_elem = soup.select_one(selectors.get('title', 'h1, .product-title'))
            if title_elem:
                product_data['title'] = title_elem.get_text(strip=True)

            # Extract price
            price_elem = soup.select_one(selectors.get('price', '.price, [data-price]'))
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                product_data['price'] = price_text
            else:
                # Try to find price in script tags or other elements
                price_text = self._find_price_in_page(soup)
                if price_text:
                    product_data['price'] = price_text

            # Extract image URL
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

        # Check page title or breadcrumbs
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

        # Default to None - will be determined by collection context
        return None
