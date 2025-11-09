#!/usr/bin/env python3
"""
Debug script to inspect Scuffers HTML structure.
"""

import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv

load_dotenv()

def inspect_scuffers_page():
    """Inspect the actual HTML structure of Scuffers page."""
    url = "https://scuffers.com/collections/all"

    headers = {
        'User-Agent': os.getenv('USER_AGENT', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    }

    print(f"Fetching: {url}")
    print(f"User-Agent: {headers['User-Agent']}")

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        print(f"Status: {response.status_code}")
        print(f"Content length: {len(response.content)}")

        soup = BeautifulSoup(response.content, 'lxml')

        # Look for common product container patterns
        potential_containers = [
            '.product-item',
            '.grid-item',
            '.product',
            '.item',
            '[class*="product"]',
            '[class*="item"]',
            'article',
            '.card',
            '[class*="card"]'
        ]

        print("\n=== Looking for product containers ===")
        for selector in potential_containers:
            elements = soup.select(selector)
            if elements:
                print(f"Found {len(elements)} elements with selector '{selector}'")
                if len(elements) <= 5:  # Show details for small numbers
                    for i, elem in enumerate(elements[:3]):
                        print(f"  Element {i+1}: {elem.get('class', 'no-class')} - {elem.get_text(strip=True)[:100]}...")
                break

        # Look for product links
        print("\n=== Looking for product links ===")
        product_links = soup.find_all('a', href=lambda x: x and '/products/' in x)
        print(f"Found {len(product_links)} links containing '/products/'")

        for i, link in enumerate(product_links[:5]):
            print(f"  Link {i+1}: {link.get('href')} - Text: {link.get_text(strip=True)[:50]}")

        # Look for price patterns
        print("\n=== Looking for price patterns ===")
        price_patterns = [
            r'\d+,\d+\s*EUR',
            r'\d+\.\d+\s*EUR',
            r'\d+,\d+',
            r'\d+\.\d+'
        ]

        text_content = soup.get_text()
        for pattern in price_patterns:
            import re
            matches = re.findall(pattern, text_content)
            if matches:
                print(f"Pattern '{pattern}' found {len(matches)} matches: {matches[:5]}")

        # Look for specific text patterns we saw in the original HTML
        print("\n=== Looking for specific Scuffers patterns ===")
        specific_texts = ['EUR', 'new in', 'NEW ', '+1']
        for text in specific_texts:
            elements_with_text = soup.find_all(string=lambda x: x and text in x.strip())
            print(f"Found {len(elements_with_text)} elements containing '{text}'")

        # Show a sample of the HTML structure
        print("\n=== Sample HTML structure ===")
        # Find the main content area
        main_content = soup.find('main') or soup.find('[role="main"]') or soup.find('.main') or soup
        if main_content:
            print("Main content preview:")
            print(str(main_content)[:1000] + "..." if len(str(main_content)) > 1000 else str(main_content))

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    inspect_scuffers_page()
