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
            max_no_change = 10  # More attempts to find new products
            scroll_attempts = 0
            max_scroll_attempts = 20  # More attempts

            while len(products) < max_products and scroll_attempts < max_scroll_attempts:
                scroll_attempts += 1

                # Focus on Load More button clicking since that's what works for Scuffers
                logger.info(f"Attempt {scroll_attempts}: Looking for Load More button...")

                # Scroll to bottom to ensure button is visible
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                await page.wait_for_timeout(2000)

                # Try multiple selectors for the Load More button
                load_more_clicked = False
                button_selectors = [
                    'button:has-text("Load More")',
                    'button:has-text("LOAD MORE")',
                    'button.button:has-text("Load More")',
                    'button.button:has-text("LOAD MORE")',
                    'button[data-load-more]',
                    '[class*="load-more"]',
                    'button:contains("Load More")',
                    'button:contains("LOAD MORE")'
                ]

                # First, log ALL buttons on the page to debug
                all_buttons = await page.query_selector_all('button')
                logger.info(f"Found {len(all_buttons)} total buttons on page")

                for i, btn in enumerate(all_buttons):
                    try:
                        text = await btn.text_content()
                        visible = await btn.is_visible()
                        if text.strip():
                            logger.info(f"  Button {i+1}: '{text.strip()}' (visible: {visible})")
                    except Exception as e:
                        logger.debug(f"Error checking button {i}: {e}")

                # Also check for any clickable elements with "load" or "more" in text
                clickable_elements = await page.query_selector_all('button, a, [role="button"], div[onclick], span[onclick]')
                load_more_candidates = []

                for elem in clickable_elements:
                    try:
                        text = await elem.text_content()
                        if text and ('load' in text.lower() or 'more' in text.lower()):
                            load_more_candidates.append(elem)
                    except:
                        pass

                logger.info(f"Found {len(load_more_candidates)} elements with 'load' or 'more' in text:")
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
                                is_visible = await button.is_visible()
                                button_text = await button.text_content()
                                button_text = button_text.strip().lower()

                                # Check if button is disabled
                                is_disabled = await button.get_attribute('disabled')
                                is_disabled = is_disabled is not None

                                if is_visible and not is_disabled and ('load more' in button_text):
                                    logger.info(f"Attempt {scroll_attempts}: Found clickable Load More button (selector: {selector}, text: '{button_text}', disabled: {is_disabled})")

                                    # Log container count before clicking
                                    product_selector = selectors.get('products', '.product-block__inner')
                                    containers_before = await page.query_selector_all(product_selector)
                                    logger.info(f"Products before click: {len(containers_before)}")

                                    # Click the button
                                    logger.info(f"Attempt {scroll_attempts}: Clicking Load More button...")
                                    await button.click()

                                    # Wait for network to be idle (AJAX requests to complete)
                                    await page.wait_for_load_state('networkidle', timeout=15000)

                                    # Additional timeout for content rendering
                                    await page.wait_for_timeout(3000)

                                    # Check if button still exists and its state
                                    try:
                                        still_visible = await button.is_visible()
                                        new_text = await button.text_content()
                                        still_disabled = await button.get_attribute('disabled')
                                        still_disabled = still_disabled is not None
                                        logger.info(f"Button after click - visible: {still_visible}, text: '{new_text.strip() if new_text else 'N/A'}', disabled: {still_disabled}")
                                    except Exception as e:
                                        logger.info(f"Button no longer exists after click: {e}")

                                    # Scroll again after clicking to ensure content loads
                                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                                    await page.wait_for_timeout(2000)

                                    load_more_clicked = True
                                    break
                            except Exception as e:
                                logger.debug(f"Error clicking button with selector {selector}: {e}")
                        if load_more_clicked:
                            break
                    except Exception as e:
                        logger.debug(f"Error with selector {selector}: {e}")

                if not load_more_clicked:
                    logger.info(f"Attempt {scroll_attempts}: No Load More button found or clickable")

                # Extract current products after potential button click
                current_products = await self._extract_products_from_page(page, selectors)

                logger.info(f"Found {len(current_products)} products after {scroll_attempts} attempts")

                # Check if we got new products
                if len(current_products) > previous_count:
                    products = current_products
                    previous_count = len(current_products)
                    no_change_count = 0
                    logger.info(f"New products found! Total: {len(products)}")
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

            logger.info(f"Final result: {len(products)} products collected after {scroll_attempts} scroll attempts")
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

            return product_data

        except Exception as e:
            logger.error(f"Error extracting product from container: {e}")
            return None
