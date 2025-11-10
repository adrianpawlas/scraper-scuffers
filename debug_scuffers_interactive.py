import asyncio
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_scuffers():
    """Debug Scuffers loading mechanism interactively"""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Set to False to see what's happening
        context = await browser.new_context()
        page = await context.new_page()

        await page.set_viewport_size({"width": 1920, "height": 1080})

        logger.info("Loading Scuffers page...")
        await page.goto("https://scuffers.com/collections/all", wait_until="networkidle")

        # Wait for initial load
        await page.wait_for_timeout(5000)

        # Check initial products
        initial_products = await page.query_selector_all('.product-block__inner')
        logger.info(f"Initial products found: {len(initial_products)}")

        # Look for load more button
        load_more_button = await page.query_selector('button:has-text("Load More")')
        if load_more_button:
            logger.info("Found Load More button")

            # Click it
            logger.info("Clicking Load More button...")
            await load_more_button.click()

            # Wait for AJAX
            await page.wait_for_timeout(10000)

            # Check products after click
            after_click_products = await page.query_selector_all('.product-block__inner')
            logger.info(f"Products after click: {len(after_click_products)}")

            # Try clicking again
            logger.info("Clicking Load More button again...")
            await load_more_button.click()
            await page.wait_for_timeout(10000)

            after_second_click_products = await page.query_selector_all('.product-block__inner')
            logger.info(f"Products after second click: {len(after_second_click_products)}")

        else:
            logger.warning("No Load More button found")

        # Let's also check the page source for any clues
        content = await page.content()
        if 'Load More' in content:
            logger.info("Load More text found in page source")
        else:
            logger.warning("Load More text NOT found in page source")

        # Check for any JavaScript errors
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg.text))

        # Try scrolling to bottom instead
        logger.info("Trying to scroll to bottom...")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        await page.wait_for_timeout(5000)

        after_scroll_products = await page.query_selector_all('.product-block__inner')
        logger.info(f"Products after scroll: {len(after_scroll_products)}")

        # Check network requests
        network_requests = []
        page.on("request", lambda request: network_requests.append(request.url) if 'scuffers' in request.url else None)

        logger.info(f"Network requests to Scuffers: {len(network_requests)}")

        # Let's check if there are any other buttons or elements that might load more
        all_buttons = await page.query_selector_all('button')
        logger.info(f"Total buttons on page: {len(all_buttons)}")

        button_texts = []
        for btn in all_buttons[:10]:  # Check first 10
            text = await btn.text_content()
            if text.strip():
                button_texts.append(text.strip())

        logger.info(f"Button texts: {button_texts}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_scuffers())
