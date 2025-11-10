import asyncio
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def inspect_buttons():
    """Inspect what buttons are actually on the Scuffers page"""

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

        # Look for ALL buttons on the page
        all_buttons = await page.query_selector_all('button')
        logger.info(f"Total buttons on page: {len(all_buttons)}")

        # Examine each button
        for i, button in enumerate(all_buttons):
            try:
                is_visible = await button.is_visible()
                text_content = await button.text_content()
                inner_text = await button.inner_text()
                outer_html = await button.evaluate("el => el.outerHTML")
                class_attr = await button.get_attribute('class')
                id_attr = await button.get_attribute('id')
                data_attrs = await button.evaluate("el => Object.keys(el.dataset)")

                logger.info(f"\nButton {i+1}:")
                logger.info(f"  Visible: {is_visible}")
                logger.info(f"  Text content: '{text_content.strip()}'")
                logger.info(f"  Inner text: '{inner_text.strip()}'")
                logger.info(f"  Class: {class_attr}")
                logger.info(f"  ID: {id_attr}")
                logger.info(f"  Data attributes: {data_attrs}")
                logger.info(f"  Outer HTML: {outer_html[:200]}...")

                # Check if it contains "load" or "more" (case insensitive)
                text_lower = text_content.lower()
                if 'load' in text_lower and 'more' in text_lower:
                    logger.info(f"  *** POTENTIAL LOAD MORE BUTTON ***")

            except Exception as e:
                logger.error(f"Error examining button {i}: {e}")

        # Also look for any element with "load more" text
        load_more_elements = await page.query_selector_all('*[text*="load more" i]')
        logger.info(f"\nElements containing 'load more' (case insensitive): {len(load_more_elements)}")

        for i, elem in enumerate(load_more_elements):
            try:
                tag_name = await elem.evaluate("el => el.tagName")
                text = await elem.text_content()
                logger.info(f"  Element {i+1}: <{tag_name}> '{text.strip()}'")
            except Exception as e:
                logger.error(f"Error examining load more element {i}: {e}")

        # Try scrolling to see if buttons appear
        logger.info("\nScrolling to bottom...")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        await page.wait_for_timeout(3000)

        after_scroll_buttons = await page.query_selector_all('button')
        logger.info(f"Buttons after scroll: {len(after_scroll_buttons)}")

        # Check if new buttons appeared
        if len(after_scroll_buttons) > len(all_buttons):
            logger.info("New buttons appeared after scrolling!")
            new_buttons = after_scroll_buttons[len(all_buttons):]
            for i, button in enumerate(new_buttons):
                try:
                    text = await button.text_content()
                    logger.info(f"  New button {i+1}: '{text.strip()}'")
                except Exception as e:
                    logger.error(f"Error examining new button {i}: {e}")

        # Look for any clickable elements with "load" in text
        clickable_elements = await page.query_selector_all('button, a, [role="button"], [onclick], [cursor="pointer"]')
        load_elements = []

        for elem in clickable_elements:
            try:
                text = await elem.text_content()
                if text and 'load' in text.lower():
                    load_elements.append(elem)
            except:
                pass

        logger.info(f"\nClickable elements containing 'load': {len(load_elements)}")
        for i, elem in enumerate(load_elements):
            try:
                tag = await elem.evaluate("el => el.tagName")
                text = await elem.text_content()
                logger.info(f"  {i+1}. <{tag}> '{text.strip()}'")
            except Exception as e:
                logger.error(f"Error examining load element {i}: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_buttons())
