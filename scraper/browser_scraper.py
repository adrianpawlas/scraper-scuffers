"""
Browser-based scraper for websites with dynamic content loading.
Uses Playwright to handle infinite scroll and AJAX-loaded content.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

from playwright.async_api import async_playwright, Browser, Page, Playwright

logger = logging.getLogger(__name__)

class BrowserScraper:
    def __init__(self, user_agent: str = None, headless: bool = True):
        self.user_agent = user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        self.headless = headless
        self.browser = None
        self.playwright = None

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def scrape_all_products(self, url: str, selectors: Dict[str, str], max_products: int = 1000) -> List[Dict[str, Any]]:
        """
        Scrape all products from a page that loads content dynamically.

        Args:
            url: Page URL to scrape
            selectors: CSS selectors for extracting product data
            max_products: Maximum number of products to collect

        Returns:
            List of product dictionaries
        """
        async with self as scraper:
            page = await self.browser.new_page()
            await page.set_viewport_size({"width": 1920, "height": 1080})

            # Set user agent
            await page.set_extra_http_headers({"User-Agent": self.user_agent})

            logger.info(f"Loading page: {url}")
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # Wait for initial content to load
            await page.wait_for_timeout(5000)

            products = []
            previous_count = 0
            no_change_count = 0
            max_no_change = 15  # More attempts to find new products (increased for safety)
            load_attempts = 0
            successful_clicks = 0
            max_load_attempts = 100  # Allow up to 100 attempts for maximum coverage

            while len(products) < max_products and load_attempts < max_load_attempts:
                load_attempts += 1

                logger.info(f"Attempt {load_attempts}: Looking for Load More button...")

                # Scroll to bottom to ensure button is visible
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                await page.wait_for_timeout(2000)

                # Try multiple selectors for the Load More button
                button_clicked = False
                button_selectors = [
                    '#load-more',  # Specific ID from HTML
                    'button[data-next-url]',  # Button with pagination data
                    'button:has-text("Load More")',
                    'button:has-text("LOAD MORE")',
                    'button:has-text("Show more")',
                    'button:has-text("SHOW MORE")',
                    'button.button:has-text("Load More")',
                    'button.button:has-text("LOAD MORE")',
                    'button.button:has-text("Show more")',
                    'button.button:has-text("SHOW MORE")',
                    'button[data-load-more]',
                    '[class*="load-more"]',
                    'button:contains("Load More")',
                    'button:contains("LOAD MORE")',
                    'button:contains("Show more")',
                    'button:contains("SHOW MORE")',
                    'button',
                    'a:has-text("Load More")',
                    'a:has-text("LOAD MORE")',
                    'a:has-text("Show more")',
                    'a:has-text("SHOW MORE")'
                ]

                # Log all clickable elements containing "load", "more", or "show"
                clickable_elements = await page.query_selector_all('button, a, [role="button"], div[onclick], span[onclick]')
                load_more_candidates = []

                for elem in clickable_elements:
                    try:
                        text = await elem.text_content()
                        if text and any(keyword in text.lower() for keyword in ['load', 'more', 'show']):
                            load_more_candidates.append(elem)
                    except:
                        pass

                logger.info(f"Found {len(load_more_candidates)} elements with 'load', 'more', or 'show' in text:")
                for i, elem in enumerate(load_more_candidates):
                    try:
                        tag = await elem.evaluate("el => el.tagName")
                        text = await elem.text_content()
                        visible = await elem.is_visible()
                        logger.info(f"  Candidate {i+1}: <{tag}> '{text.strip()}' (visible: {visible})")
                    except Exception as e:
                        logger.debug(f"Error checking candidate {i}: {e}")

                for selector in button_selectors:
                    try:
                        buttons = await page.query_selector_all(selector)
                        for button in buttons:
                            try:
                                text = await button.text_content()
                                text = text.strip().lower() if text else ""

                                if 'load more' in text or 'show more' in text:
                                    # First, try to scroll the button into view
                                    try:
                                        await button.scroll_into_view_if_needed()
                                        await page.wait_for_timeout(1000)  # Wait for scroll to complete
                                        logger.info("Scrolled button into view")
                                    except Exception as e:
                                        logger.warning(f"Failed to scroll button into view: {e}")

                                    is_visible = await button.is_visible()
                                    is_disabled = await button.get_attribute('disabled')
                                    is_disabled = is_disabled is not None
                                    next_url = await button.get_attribute('data-next-url')

                                    logger.info(f"Found potential button: '{text}' (visible: {is_visible}, disabled: {is_disabled}, next-url: {next_url})")

                                    # Stop if button is disabled or has no next URL (indicates no more content)
                                    if is_disabled:
                                        logger.info("Button is disabled - no more content to load")
                                        button_clicked = True  # Set to true to break out of loop
                                        break
                                    elif next_url == "" or next_url is None:
                                        logger.info("Button has no next URL - likely no more content to load")
                                        # Still try clicking once to be sure, but don't count as successful
                                        pass

                                    # Try clicking even if not visible initially
                                    if not is_disabled:
                                        logger.info(f"Attempt {load_attempts}: Clicking {text} button...")

                                        # Try multiple click methods
                                        click_success = False
                                        try:
                                            # Method 1: Direct click
                                            await button.click()
                                            logger.info("Used direct click")
                                            click_success = True
                                        except Exception as e:
                                            logger.warning(f"Direct click failed: {e}")
                                            try:
                                                # Method 2: JavaScript click
                                                await button.evaluate("el => el.click()")
                                                logger.info("Used JavaScript click")
                                                click_success = True
                                            except Exception as e2:
                                                logger.warning(f"JavaScript click failed: {e2}")
                                                try:
                                                    # Method 3: Dispatch click event
                                                    await button.dispatch_event('click')
                                                    logger.info("Used dispatch click event")
                                                    click_success = True
                                                except Exception as e3:
                                                    logger.error(f"All click methods failed: {e3}")

                                        if click_success:
                                            successful_clicks += 1
                                            logger.info(f"✅ Successful click #{successful_clicks} on '{text}' button")

                                            # Wait for network activity to settle
                                            await page.wait_for_load_state('networkidle', timeout=15000)

                                            # Additional wait for content to load
                                            await page.wait_for_timeout(5000)

                                            # Check if button is still visible (might disappear after loading all)
                                            try:
                                                still_visible = await button.is_visible()
                                                logger.info(f"Button still visible after click: {still_visible}")
                                            except:
                                                logger.info("Button no longer exists after click")

                                            button_clicked = True
                                            break
                            except Exception as e:
                                logger.debug(f"Error processing button: {e}")
                        if button_clicked:
                            break
                    except Exception as e:
                        logger.debug(f"Error with selector {selector}: {e}")

                if not button_clicked:
                    logger.info(f"Attempt {load_attempts}: No clickable Load More button found")
                    # If no button found after first few attempts, stop trying
                    # Allow more attempts since we want maximum coverage
                    if load_attempts >= 15:
                        logger.info("No Load More button found after multiple attempts, stopping")
                        break

                # Extract current products after potential button click
                current_products = await self._extract_products_from_page(page, selectors)
                logger.info(f"Found {len(current_products)} products after attempt {load_attempts}")

                # Check if we got new products
                if len(current_products) > previous_count:
                    products = current_products
                    previous_count = len(current_products)
                    no_change_count = 0
                    progress_msg = f"New products found! Total: {len(products)}"
                    if len(products) >= 1300:
                        progress_msg += " 🎯 Almost there!"
                    elif len(products) >= 1000:
                        progress_msg += f" (target: 1321, {1321 - len(products)} remaining)"
                    logger.info(progress_msg)
                else:
                    no_change_count += 1
                    logger.info(f"No new products found (attempt {no_change_count}/{max_no_change})")

                    if no_change_count >= max_no_change:
                        logger.info("Stopping - no more products loading after multiple attempts")
                        break

                # Safety check to avoid infinite loops
                if len(products) >= max_products:
                    logger.info(f"Reached maximum product limit: {max_products}")
                    break

            logger.info(f"Final result: {len(products)} products collected after {load_attempts} load attempts, {successful_clicks} successful clicks")
            if len(products) >= 1300:
                logger.info("🎉 Excellent! Reached or exceeded target of 1321 products!")
            elif len(products) >= 1000:
                logger.info(f"✅ Good progress! Got {len(products)} products, close to the 1321 target")
            else:
                logger.info(f"📊 Got {len(products)} products. Target is 1321 - may need more attempts")
            await page.close()
            return products[:max_products]


    async def _extract_products_from_page(self, page: Page, selectors: Dict[str, str]) -> List[Dict[str, Any]]:
        """Extract product data from the current page state."""
        product_selector = selectors.get('products', '.product-block__inner')

        # Get all product containers
        containers = await page.query_selector_all(product_selector)

        products = []
        for i, container in enumerate(containers):
            try:
                product_data = await self._extract_product_from_container(container, page, selectors)
                if product_data:
                    products.append(product_data)
            except Exception as e:
                logger.warning(f"Failed to extract product {i}: {e}")

        return products

    async def _extract_product_from_container(self, container, page: Page, selectors: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Extract product data from a single container element."""
        try:
            # Extract product URL
            link_elem = await container.query_selector(selectors.get('product_url', 'a[href*="/products/"]'))
            if not link_elem:
                return None

            product_url = await link_elem.get_attribute('href')
            if product_url:
                if product_url.startswith('/'):
                    base_url = page.url.split('/collections')[0]  # Get base URL
                    product_url = urljoin(base_url, product_url)

            product_data = {
                'product_url': product_url,
                'external_id': product_url.split('/')[-1] if product_url else None
            }

            # Extract title
            title_elem = await container.query_selector(selectors.get('title', 'h1, .product-title, .title'))
            if title_elem:
                title_text = await title_elem.text_content()
                if title_text:
                    product_data['title'] = title_text.strip()

            # Extract price
            price_elem = await container.query_selector(selectors.get('price', '.price, .product-price'))
            if price_elem:
                price_text = await price_elem.text_content()
                if price_text:
                    product_data['price'] = price_text.strip()

            # Extract image URL
            img_elem = await container.query_selector(selectors.get('image_url', 'img'))
            if img_elem:
                img_url = await img_elem.get_attribute('src')
                if img_url:
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        base_url = page.url.split('/collections')[0]
                        img_url = urljoin(base_url, img_url)
                    product_data['image_url'] = img_url

            # Extract gender
            gender = await self._determine_gender(container, page, selectors, product_url)
            if gender:
                product_data['gender'] = gender

            return product_data

        except Exception as e:
            logger.error(f"Error extracting product from container: {e}")
            return None

    async def _determine_gender(self, container, page: Page, selectors: Dict[str, str], product_url: str) -> Optional[str]:
        """
        Determine product gender from page and container content.

        Args:
            container: Product container element
            page: Playwright page object
            selectors: CSS selectors
            product_url: Product URL

        Returns:
            'men', 'women', or None
        """
        try:
            # Check URL for gender indicators
            url_lower = product_url.lower()
            if 'women' in url_lower or 'woman' in url_lower or 'female' in url_lower:
                return 'women'
            elif 'men' in url_lower or 'man' in url_lower or 'male' in url_lower:
                return 'men'

            # Check page title
            title_elem = await page.query_selector('title')
            if title_elem:
                title_text = await title_elem.text_content()
                title_lower = title_text.lower()
                if 'women' in title_lower or 'woman' in title_lower:
                    return 'women'
                elif 'men' in title_lower or 'man' in title_lower:
                    return 'men'

            # Check meta description
            meta_desc = await page.query_selector('meta[name="description"]')
            if meta_desc:
                desc_content = await meta_desc.get_attribute('content')
                if desc_content:
                    desc_lower = desc_content.lower()
                    if '(man)' in desc_lower or '(male)' in desc_lower or 'man wearing' in desc_lower:
                        return 'men'
                    elif '(woman)' in desc_lower or '(female)' in desc_lower or 'woman wearing' in desc_lower:
                        return 'women'

            # Check breadcrumbs for gender context
            breadcrumbs = await page.query_selector_all('.breadcrumb, .breadcrumbs, [class*="breadcrumb"]')
            for crumb in breadcrumbs:
                try:
                    crumb_text = await crumb.text_content()
                    crumb_lower = crumb_text.lower()
                    if 'women' in crumb_lower or 'woman' in crumb_lower or 'female' in crumb_lower:
                        return 'women'
                    elif 'men' in crumb_lower or 'man' in crumb_lower or 'male' in crumb_lower:
                        return 'men'
                except:
                    continue

            # Check specific gender selectors
            gender_selector = selectors.get('gender', '.gender, .category, .collection-title, h1')
            gender_elem = await page.query_selector(gender_selector)
            if gender_elem:
                gender_text = await gender_elem.text_content()
                gender_lower = gender_text.lower()
                if 'women' in gender_lower or 'woman' in gender_lower or 'female' in gender_lower:
                    return 'women'
                elif 'men' in gender_lower or 'man' in gender_lower or 'male' in gender_lower:
                    return 'men'

            # Check product title for gender indicators
            title_elem = await container.query_selector(selectors.get('title', 'h1, .product-title, .title'))
            if title_elem:
                title_text = await title_elem.text_content()
                title_lower = title_text.lower()
                if any(term in title_lower for term in ['men\'s', 'man\'s', 'male', 'for men', 'men only']):
                    return 'men'
                elif any(term in title_lower for term in ['women\'s', 'woman\'s', 'female', 'for women', 'women only']):
                    return 'women'
                elif 'unisex' in title_lower:
                    return None  # Could be either

            # Check product description for gender indicators
            desc_elem = await container.query_selector('.product-description, .description, [class*="description"]')
            if desc_elem:
                desc_text = await desc_elem.text_content()
                desc_lower = desc_text.lower()
                if any(term in desc_lower for term in ['men\'s', 'man\'s', 'male', 'unisex']):
                    if 'unisex' in desc_lower:
                        return None  # Could be either
                    elif any(term in desc_lower for term in ['men\'s', 'man\'s', 'male']):
                        return 'men'
                elif any(term in desc_lower for term in ['women\'s', 'woman\'s', 'female']):
                    return 'women'

            # Check for collection/category context in URL
            page_url = page.url.lower()
            if '/collections/women' in page_url or '/women' in page_url:
                return 'women'
            elif '/collections/men' in page_url or '/men' in page_url:
                return 'men'

            # Default to None - will be determined by collection context if needed
            return None

        except Exception as e:
            logger.debug(f"Error determining gender for {product_url}: {e}")
            return None
