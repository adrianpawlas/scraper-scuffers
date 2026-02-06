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
            await page.goto(url, wait_until="domcontentloaded", timeout=180000)  # Increased timeout for slow sites

            # Wait for initial content to load
            await page.wait_for_timeout(5000)

            # Handle cookie consent dialogs that might block interactions
            await self._handle_cookie_consent(page)

            products = []
            previous_count = 0
            no_change_count = 0
            max_no_change = 50  # Allow more attempts since we need to load many products (increased from 15)
            load_attempts = 0
            successful_clicks = 0
            max_load_attempts = 200  # Allow up to 200 attempts for maximum coverage (increased from 100)

            while len(products) < max_products and load_attempts < max_load_attempts:
                load_attempts += 1

                logger.info(f"Attempt {load_attempts}: Looking for Load More button...")

                # Scroll to bottom to ensure button is visible
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                await page.wait_for_timeout(2000)

                # Handle any cookie overlays that might have appeared
                await self._handle_cookie_consent(page)

                # Try multiple selectors for the Load More button
                button_clicked = False
                button_selectors = [
                    '#load-more',  # Specific ID from HTML
                    'button[data-next-url]',  # Button with pagination data
                    'button:has-text("Load More")',
                    'button:has-text("LOAD MORE")',
                    'button:has-text("Show more")',
                    'button:has-text("SHOW MORE")',
                    'button:has-text("Cargar más")',  # Spanish
                    'button:has-text("CARGAR MÁS")',
                    'button:has-text("Load more")',  # Lowercase variations
                    'button:has-text("Show more")',
                    'button.button:has-text("Load More")',
                    'button.button:has-text("LOAD MORE")',
                    'button.button:has-text("Show more")',
                    'button.button:has-text("SHOW MORE")',
                    'button.button:has-text("Cargar más")',
                    'button.button:has-text("CARGAR MÁS")',
                    'button[data-load-more]',
                    '[class*="load-more"]',
                    'button:contains("Load More")',
                    'button:contains("LOAD MORE")',
                    'button:contains("Show more")',
                    'button:contains("SHOW MORE")',
                    'button:contains("Cargar más")',
                    'button:contains("CARGAR MÁS")',
                    'button:contains("Charger plus")',  # French
                    'button:contains("CHARGER PLUS")',
                    'button:contains("Mehr laden")',  # German
                    'button:contains("MEHR LADEN")',
                    'button:contains("Carica altro")',  # Italian
                    'button:contains("CARICA ALTRO")',
                    'button',
                    'a:has-text("Load More")',
                    'a:has-text("LOAD MORE")',
                    'a:has-text("Show more")',
                    'a:has-text("SHOW MORE")',
                    'a:has-text("Cargar más")',
                    'a:has-text("CARGAR MÁS")'
                ]

                # Log all clickable elements containing load/more/show keywords in multiple languages
                clickable_elements = await page.query_selector_all('button, a, [role="button"], div[onclick], span[onclick]')
                load_more_candidates = []

                # Keywords in multiple languages
                load_more_keywords = [
                    'load', 'more', 'show', 'cargar', 'charger', 'laden', 'carica',  # English, Spanish, French, German, Italian
                    'más', 'plus', 'altro', 'mehr'  # Additional words
                ]

                for elem in clickable_elements:
                    try:
                        text = await elem.text_content()
                        if text and any(keyword in text.lower() for keyword in load_more_keywords):
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

                                # Prioritize "load" buttons over "show" buttons, and include Spanish
                                is_load_button = any(phrase in text for phrase in [
                                    'load more', 'cargar más', 'charger plus', 'mehr laden', 'carica altro'
                                ])
                                is_show_button = 'show more' in text and not is_load_button

                                if is_load_button or is_show_button:
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

                                        # Handle any overlays before clicking
                                        await self._handle_cookie_consent(page)

                                        # Try multiple click methods
                                        click_success = False
                                        try:
                                            # Method 1: Direct click with force
                                            await button.click(timeout=10000, force=True)  # Force click ignores overlays
                                            logger.info("Used direct click (force)")
                                            click_success = True
                                        except Exception as e:
                                            logger.warning(f"Direct click failed: {e}")
                                            try:
                                                # Method 2: JavaScript click with overlay removal
                                                click_script = """
                                                (el) => {
                                                    // Remove all potential overlays
                                                    const overlaySelectors = [
                                                        // Cookie overlays
                                                        '.cky-overlay', '.cky-consent-container', '[class*="cky-consent"]',
                                                        '.cookie-banner', '.gdpr-banner', '#cookie-banner',

                                                        // General overlays
                                                        '.modal', '.popup', '.overlay', '.lightbox',

                                                        // Specific popups
                                                        '.newsletter-popup', '.discount-popup', '.promo-popup', '.sale-popup',
                                                        '.announcement-bar', '.notification-bar', '.alert-bar',

                                                        // Sale/discount specific
                                                        '[class*="sale-banner"]', '[id*="sale-popup"]', '[class*="offer-popup"]',
                                                        '.exit-popup', '.welcome-popup', '.subscription-popup'
                                                    ];

                                                    overlaySelectors.forEach(selector => {
                                                        const elements = document.querySelectorAll(selector);
                                                        elements.forEach(el => {
                                                            el.style.display = 'none';
                                                            el.remove();
                                                        });
                                                    });

                                                    // Click the element
                                                    el.scrollIntoView();
                                                    el.click();
                                                    return true;
                                                }
                                                """
                                                await button.evaluate(click_script)
                                                logger.info("Used JavaScript click with overlay removal")
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
                                            await page.wait_for_load_state('networkidle', timeout=20000)

                                            # Additional wait for content to load (increased for slow loading)
                                            await page.wait_for_timeout(8000)

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


    async def _handle_cookie_consent(self, page: Page):
        """Handle cookie consent dialogs that might block interactions."""
        try:
            logger.info("Checking for cookie consent dialogs...")

            # First try to accept cookies
            cookie_selectors = [
                'button[data-cky-tag="accept-button"]',
                '.cky-btn-accept',
                'button.cky-btn-accept',
                'button:has-text("Accept All")',
                'button:has-text("ACCEPT ALL")',
                'button:has-text("Accept")',
                'button:has-text("ACCEPT")',
                'button:has-text("Agree")',
                'button:has-text("AGREE")',
                'button:has-text("Allow All")',
                'button:has-text("ALLOW ALL")',
                'button:has-text("Yes")',
                'button:has-text("YES")',
                '[class*="accept"]',
                '[class*="agree"]',
                'a.cky-btn-accept'
            ]

            # First handle discount/sale popups that might be blocking
            discount_selectors = [
                'button:has-text("No thanks")',
                'button:has-text("NO THANKS")',
                'button:has-text("Close")',
                'button:has-text("CLOSE")',
                'button:has-text("×")',
                'button:has-text("X")',
                'button:has-text("✕")',
                '.discount-popup .close',
                '.sale-popup .close',
                '.promo-popup .close',
                '[class*="discount"] .close',
                '[class*="promo"] .close',
                '[class*="sale"] .close'
            ]

            for selector in discount_selectors:
                try:
                    close_buttons = await page.query_selector_all(selector)
                    for button in close_buttons:
                        try:
                            is_visible = await button.is_visible()
                            if is_visible:
                                logger.info(f"Found discount popup close button: {selector}")
                                await button.click(timeout=2000)
                                logger.info("Closed discount popup")
                                await page.wait_for_timeout(500)
                                break
                        except:
                            continue
                except Exception as e:
                    logger.debug(f"Discount popup selector {selector} failed: {e}")
                    continue

            # Then handle cookie consent
            for selector in cookie_selectors:
                try:
                    accept_buttons = await page.query_selector_all(selector)
                    for button in accept_buttons:
                        try:
                            is_visible = await button.is_visible()
                            if is_visible:
                                logger.info(f"Found cookie consent button: {selector}")
                                # Try direct click first
                                try:
                                    await button.click(timeout=2000)
                                    logger.info("Accepted cookie consent via direct click")
                                    await page.wait_for_timeout(1000)
                                    return
                                except:
                                    # Try JavaScript click
                                    try:
                                        await button.evaluate("el => el.click()")
                                        logger.info("Accepted cookie consent via JavaScript click")
                                        await page.wait_for_timeout(1000)
                                        return
                                    except:
                                        pass
                        except:
                            continue
                except Exception as e:
                    logger.debug(f"Cookie consent selector {selector} failed: {e}")
                    continue

            # If accepting didn't work, try to remove/hide the overlay entirely
            logger.info("Cookie acceptance failed, trying to remove overlay...")
            overlay_removal_script = """
            // Remove common overlay elements including discount popups
            const overlaySelectors = [
                // Cookie overlays
                '.cky-overlay', '.cky-consent-container', '[class*="cky-consent"]',
                '.cookie-banner', '.gdpr-banner', '#cookie-banner',
                '.cookie-consent', '.gdpr-consent', '[class*="cookie-popup"]',

                // General overlays
                '.modal', '.popup', '.overlay', '.lightbox',

                // Specific popups
                '.newsletter-popup', '.discount-popup', '.promo-popup', '.sale-popup',
                '.announcement-bar', '.notification-bar', '.alert-bar',

                // Generic selectors
                '[class*="modal"]', '[class*="popup"]', '[class*="overlay"]',
                '[id*="modal"]', '[id*="popup"]', '[id*="overlay"]',
                '[class*="newsletter"]', '[class*="discount"]', '[class*="promo"]',
                '[class*="announcement"]', '[class*="notification"]',

                // Sale/discount specific
                '[class*="sale-banner"]', '[id*="sale-popup"]', '[class*="offer-popup"]',
                '.exit-popup', '.welcome-popup', '.subscription-popup'
            ];

            overlaySelectors.forEach(selector => {
                const elements = document.querySelectorAll(selector);
                elements.forEach(el => {
                    el.style.display = 'none';
                    el.remove();
                });
            });

            // Hide any fixed/absolute positioned elements that might overlay
            const allElements = document.querySelectorAll('*');
            allElements.forEach(el => {
                const style = window.getComputedStyle(el);
                if ((style.position === 'fixed' || style.position === 'absolute') &&
                    (parseInt(style.zIndex) > 1000 || style.zIndex === '9999')) {
                    // Check if it looks like an overlay/popup/modal
                    if (el.classList.contains('cky') || el.id.includes('cky') ||
                        el.classList.contains('cookie') || el.id.includes('cookie') ||
                        el.classList.contains('modal') || el.classList.contains('popup') ||
                        el.classList.contains('overlay') || el.classList.contains('lightbox') ||
                        el.classList.contains('newsletter') || el.classList.contains('discount') ||
                        el.classList.contains('promo') || el.classList.contains('announcement') ||
                        el.classList.contains('notification') || el.classList.contains('alert') ||
                        el.classList.contains('sale') || el.classList.contains('offer') ||
                        el.classList.contains('welcome') || el.classList.contains('subscription') ||
                        el.classList.contains('exit')) {
                        el.style.display = 'none';
                    }
                }
            });

            return true;
            """

            try:
                await page.evaluate(overlay_removal_script)
                logger.info("Removed cookie overlay via JavaScript")
                await page.wait_for_timeout(500)
            except Exception as e:
                logger.debug(f"Overlay removal failed: {e}")

        except Exception as e:
            logger.debug(f"Cookie consent handling failed: {e}")

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

    def _is_desired_image(self, img_url: str) -> bool:
        """
        Filter image URLs to only include desired ones.
        Based on analysis of right vs wrong image patterns from Scuffers.
        """
        if not img_url:
            return False

        # Extract filename from URL
        filename = img_url.split('/')[-1].split('?')[0]  # Remove query params

        # Exclude images with UUIDs (long alphanumeric strings)
        # Pattern: contains 32+ character hex-like string (UUID format)
        import re
        if re.search(r'[a-f0-9]{32,}', filename):
            return False

        # Exclude images that start with numeric codes like "03_", "DROP_16_", etc.
        if re.match(r'^\d+_', filename):
            return False

        # Exclude images that start with "DROP_" or "CO" prefixes
        if filename.startswith(('DROP_', 'CO')):
            return False

        # Exclude images that are just numeric codes
        if re.match(r'^[A-Z]{2,}\d+\.jpg$', filename):
            return False

        # Include images that have meaningful product names
        # Should contain actual product descriptors
        meaningful_patterns = [
            'pants', 'knit', 'zipper', 'jacket', 'shirt', 'coat', 'dress', 'skirt',
            'jeans', 'short', 'sweater', 'top', 'boot', 'shoe', 'sneaker', 'hat',
            'cap', 'bag', 'belt', 'wallet', 'scarf', 'jewelry', 'accessory',
            'blue', 'red', 'black', 'white', 'green', 'dark', 'light'
        ]

        # Check if filename contains meaningful product terms
        filename_lower = filename.lower()
        has_meaningful_name = any(pattern in filename_lower for pattern in meaningful_patterns)

        # Must have at least 2 meaningful parts (separated by underscores)
        parts = filename.replace('.jpg', '').split('_')
        has_multiple_parts = len(parts) >= 2

        # Additional check: exclude images that look like secondary variants
        # If filename ends with _2, _3, etc., be more restrictive
        if re.search(r'_\d+\.jpg$', filename) and filename.split('_')[-1].replace('.jpg', '').isdigit():
            variant_num = int(filename.split('_')[-1].replace('.jpg', ''))
            if variant_num > 2:  # Only allow _1 and _2
                return False

        return has_meaningful_name and has_multiple_parts

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

            # Extract price (full text for multi-currency: "20 USD, 450 CZK, 75 PLN")
            price_elem = await container.query_selector(selectors.get('price', '.price, .product-price'))
            if price_elem:
                price_text = await price_elem.text_content()
                if price_text:
                    product_data['price'] = price_text.strip()

            # Extract sale price (same format; only set if product is on sale)
            sale_selector = selectors.get('sale', '.sale-price, .price--sale, [data-sale-price], .compare-at-price')
            sale_elem = await container.query_selector(sale_selector)
            if sale_elem:
                sale_text = (await sale_elem.text_content() or '').strip()
                if sale_text and sale_text != product_data.get('price'):
                    product_data['sale'] = sale_text

            # Extract all image URLs from this container (each product gets its own images)
            img_elems = await container.query_selector_all(selectors.get('image_url', 'img'))
            product_images = []
            base_url = page.url.split('/collections')[0] if '/collections' in page.url else page.url.rsplit('/', 1)[0]
            for img_el in img_elems:
                img_url = await img_el.get_attribute('src') or await img_el.get_attribute('data-src')
                if img_url:
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = urljoin(base_url, img_url)
                    if self._is_desired_image(img_url) and img_url not in product_images:
                        product_images.append(img_url)
            if product_images:
                product_data['image_url'] = product_images[0]
                if len(product_images) > 1:
                    product_data['additional_images'] = ','.join(product_images[1:])

            # Extract gender and category
            gender, category = await self._determine_category(container, page, selectors, product_url)
            if gender:
                product_data['gender'] = gender
            if category:
                product_data['category'] = category

            # Skip products without suitable images
            if 'image_url' not in product_data:
                logger.debug(f"Skipping product {product_data.get('external_id', 'unknown')} - no suitable image found")
                return None

            return product_data

        except Exception as e:
            logger.error(f"Error extracting product from container: {e}")
            return None

    async def _determine_category(self, container, page: Page, selectors: Dict[str, str], product_url: str) -> tuple[Optional[str], Optional[str]]:
        """
        Determine product gender and category from page and container content.

        Args:
            container: Product container element
            page: Playwright page object
            selectors: CSS selectors
            product_url: Product URL

        Returns:
            Tuple of (gender, category) where:
            - gender: 'men', 'women', or None
            - category: 'accessory', 'footwear', 'other', or None
        """
        try:
            gender = None
            category_type = None

            # Check URL for both gender and category indicators
            url_lower = product_url.lower()

            # Gender detection
            if 'women' in url_lower or 'woman' in url_lower or 'female' in url_lower:
                gender = 'women'
            elif 'men' in url_lower or 'man' in url_lower or 'male' in url_lower:
                gender = 'men'

            # Category detection
            if any(term in url_lower for term in ['accessory', 'accessories', 'bag', 'bags', 'jewelry', 'hat', 'cap', 'scarf', 'belt', 'wallet']):
                category_type = 'accessory'
            elif any(term in url_lower for term in ['shoe', 'shoes', 'boot', 'boots', 'sneaker', 'sneakers', 'footwear', 'sandal', 'sandals']):
                category_type = 'footwear'
            elif any(term in url_lower for term in ['jacket', 'coat', 'shirt', 'top', 'dress', 'skirt', 'pants', 'trousers', 'jeans', 'short', 'sweater']):
                category_type = 'clothing'

            # Check page title
            title_elem = await page.query_selector('title')
            if title_elem:
                title_text = await title_elem.text_content()
                title_lower = title_text.lower()

                # Gender detection
                if not gender:
                    if 'women' in title_lower or 'woman' in title_lower:
                        gender = 'women'
                    elif 'men' in title_lower or 'man' in title_lower:
                        gender = 'men'

                # Category detection
                if not category_type:
                    if any(term in title_lower for term in ['accessory', 'accessories', 'bag', 'bags', 'jewelry', 'hat', 'cap', 'scarf', 'belt', 'wallet']):
                        category_type = 'accessory'
                    elif any(term in title_lower for term in ['shoe', 'shoes', 'boot', 'boots', 'sneaker', 'sneakers', 'footwear', 'sandal', 'sandals']):
                        category_type = 'footwear'
                    elif any(term in title_lower for term in ['jacket', 'coat', 'shirt', 'top', 'dress', 'skirt', 'pants', 'trousers', 'jeans', 'short', 'sweater']):
                        category_type = 'clothing'

            # Check meta description
            meta_desc = await page.query_selector('meta[name="description"]')
            if meta_desc:
                desc_content = await meta_desc.get_attribute('content')
                if desc_content:
                    desc_lower = desc_content.lower()

                    # Gender detection
                    if not gender:
                        if '(man)' in desc_lower or '(male)' in desc_lower or 'man wearing' in desc_lower:
                            gender = 'men'
                        elif '(woman)' in desc_lower or '(female)' in desc_lower or 'woman wearing' in desc_lower:
                            gender = 'women'

                    # Category detection
                    if not category_type:
                        if any(term in desc_lower for term in ['accessory', 'accessories', 'bag', 'bags', 'jewelry', 'hat', 'cap', 'scarf', 'belt', 'wallet']):
                            category_type = 'accessory'
                        elif any(term in desc_lower for term in ['shoe', 'shoes', 'boot', 'boots', 'sneaker', 'sneakers', 'footwear', 'sandal', 'sandals']):
                            category_type = 'footwear'
                        elif any(term in desc_lower for term in ['jacket', 'coat', 'shirt', 'top', 'dress', 'skirt', 'pants', 'trousers', 'jeans', 'short', 'sweater']):
                            category_type = 'clothing'

            # Check breadcrumbs
            breadcrumbs = await page.query_selector_all('.breadcrumb, .breadcrumbs, [class*="breadcrumb"]')
            for crumb in breadcrumbs:
                try:
                    crumb_text = await crumb.text_content()
                    crumb_lower = crumb_text.lower()

                    # Gender detection
                    if not gender:
                        if 'women' in crumb_lower or 'woman' in crumb_lower or 'female' in crumb_lower:
                            gender = 'women'
                        elif 'men' in crumb_lower or 'man' in crumb_lower or 'male' in crumb_lower:
                            gender = 'men'

                    # Category detection
                    if not category_type:
                        if any(term in crumb_lower for term in ['accessory', 'accessories', 'bag', 'bags', 'jewelry', 'hat', 'cap', 'scarf', 'belt', 'wallet']):
                            category_type = 'accessory'
                        elif any(term in crumb_lower for term in ['shoe', 'shoes', 'boot', 'boots', 'sneaker', 'sneakers', 'footwear', 'sandal', 'sandals']):
                            category_type = 'footwear'
                        elif any(term in crumb_lower for term in ['jacket', 'coat', 'shirt', 'top', 'dress', 'skirt', 'pants', 'trousers', 'jeans', 'short', 'sweater']):
                            category_type = 'clothing'
                except:
                    continue

            # Check specific selectors
            gender_selector = selectors.get('gender', '.gender, .category, .collection-title, h1')
            gender_elem = await page.query_selector(gender_selector)
            if gender_elem:
                gender_text = await gender_elem.text_content()
                gender_lower = gender_text.lower()

                # Gender detection
                if not gender:
                    if 'women' in gender_lower or 'woman' in gender_lower or 'female' in gender_lower:
                        gender = 'women'
                    elif 'men' in gender_lower or 'man' in gender_lower or 'male' in gender_lower:
                        gender = 'men'

                # Category detection
                if not category_type:
                    if any(term in gender_lower for term in ['accessory', 'accessories', 'bag', 'bags', 'jewelry', 'hat', 'cap', 'scarf', 'belt', 'wallet']):
                        category_type = 'accessory'
                    elif any(term in gender_lower for term in ['shoe', 'shoes', 'boot', 'boots', 'sneaker', 'sneakers', 'footwear', 'sandal', 'sandals']):
                        category_type = 'footwear'
                    elif any(term in gender_lower for term in ['jacket', 'coat', 'shirt', 'top', 'dress', 'skirt', 'pants', 'trousers', 'jeans', 'short', 'sweater']):
                        category_type = 'clothing'

            # Check product title
            title_elem = await container.query_selector(selectors.get('title', 'h1, .product-title, .title'))
            if title_elem:
                title_text = await title_elem.text_content()
                title_lower = title_text.lower()

                # Gender detection
                if not gender:
                    if any(term in title_lower for term in ['men\'s', 'man\'s', 'male', 'for men', 'men only']):
                        gender = 'men'
                    elif any(term in title_lower for term in ['women\'s', 'woman\'s', 'female', 'for women', 'women only']):
                        gender = 'women'
                    elif 'unisex' in title_lower:
                        gender = None  # Could be either

                # Category detection
                if not category_type:
                    if any(term in title_lower for term in ['accessory', 'accessories', 'bag', 'bags', 'jewelry', 'hat', 'cap', 'scarf', 'belt', 'wallet']):
                        category_type = 'accessory'
                    elif any(term in title_lower for term in ['shoe', 'shoes', 'boot', 'boots', 'sneaker', 'sneakers', 'footwear', 'sandal', 'sandals']):
                        category_type = 'footwear'
                    elif any(term in title_lower for term in ['jacket', 'coat', 'shirt', 'top', 'dress', 'skirt', 'pants', 'trousers', 'jeans', 'short', 'sweater']):
                        category_type = 'clothing'

            # Check product description
            desc_elem = await container.query_selector('.product-description, .description, [class*="description"]')
            if desc_elem:
                desc_text = await desc_elem.text_content()
                desc_lower = desc_text.lower()

                # Gender detection
                if not gender:
                    if any(term in desc_lower for term in ['men\'s', 'man\'s', 'male']):
                        gender = 'men'
                    elif any(term in desc_lower for term in ['women\'s', 'woman\'s', 'female']):
                        gender = 'women'
                    elif 'unisex' in desc_lower:
                        gender = None

                # Category detection
                if not category_type:
                    if any(term in desc_lower for term in ['accessory', 'accessories', 'bag', 'bags', 'jewelry', 'hat', 'cap', 'scarf', 'belt', 'wallet']):
                        category_type = 'accessory'
                    elif any(term in desc_lower for term in ['shoe', 'shoes', 'boot', 'boots', 'sneaker', 'sneakers', 'footwear', 'sandal', 'sandals']):
                        category_type = 'footwear'
                    elif any(term in desc_lower for term in ['jacket', 'coat', 'shirt', 'top', 'dress', 'skirt', 'pants', 'trousers', 'jeans', 'short', 'sweater']):
                        category_type = 'clothing'

            # Check collection/category context in URL
            page_url = page.url.lower()
            if not gender:
                if '/collections/women' in page_url or '/women' in page_url:
                    gender = 'women'
                elif '/collections/men' in page_url or '/men' in page_url:
                    gender = 'men'

            if not category_type:
                if any(term in page_url for term in ['/accessories', '/bags', '/jewelry', '/hats', '/scarves', '/belts', '/wallets']):
                    category_type = 'accessory'
                elif any(term in page_url for term in ['/shoes', '/boots', '/sneakers', '/footwear', '/sandals']):
                    category_type = 'footwear'
                elif any(term in page_url for term in ['/clothing', '/tops', '/bottoms', '/dresses', '/jackets']):
                    category_type = 'clothing'

            # Determine final category
            final_category = None
            if category_type and category_type != 'clothing':  # Don't save 'clothing' as it's the default
                final_category = category_type
            elif not gender:
                # If no gender detected and no specific category, mark as 'other'
                final_category = 'other'

            return gender, final_category

        except Exception as e:
            logger.debug(f"Error determining category for {product_url}: {e}")
            return None
