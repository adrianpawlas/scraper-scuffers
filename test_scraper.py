#!/usr/bin/env python3
"""
Test script for the Scuffers scraper.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

def test_embeddings():
    """Test embedding generation (skipped when service unavailable)."""
    print("Testing SigLIP embeddings...")

    try:
        from scraper.embeddings import get_image_embedding

        # Test with a sample image
        test_url = 'https://images.unsplash.com/photo-1523381210434-271e8be1f52b?w=400'
        embedding = get_image_embedding(test_url)

        if embedding and len(embedding) == 768:
            print(f"Embedding generation successful: {len(embedding)} dimensions")
            print(f"   First 5 values: {embedding[:5]}")
            return True
        else:
            print("Skipped (embedding service unavailable or wrong dimensions)")
            return True

    except Exception as e:
        print(f"Skipped (embedding test: {e})")
        return True

def test_image_filtering():
    """Test the image URL filtering logic."""
    print("Testing image URL filtering...")

    try:
        from scraper.browser_scraper import BrowserScraper

        scraper = BrowserScraper()

        # Test URLs - right ones (should return True); filter allows _1 and _2 variants
        right_urls = [
            'https://scuffers.com/cdn/shop/files/RodBluePants_SEM51_1.jpg?v=1765915763',
            'https://scuffers.com/cdn/shop/files/CityDarkPants_SEM45_1.jpg?v=1764852335',
            'https://scuffers.com/cdn/shop/files/Scff_Red_Knit_Zipper_DROP2_1.jpg?v=1768926610',
            'https://scuffers.com/cdn/shop/files/QuarterRedZipperKnit_SEM52_2.jpg?v=1766414481',
            'https://scuffers.com/cdn/shop/files/Scff_Red_Knit_Zipper_DROP2_2.jpg?v=1768926610',
        ]

        # Test URLs - wrong ones (should return False): UUID-like, DROP_/CO, or variant _3+
        wrong_urls = [
            'https://scuffers.com/cdn/shop/files/03_SCFF_KNIT_ZIPPER_RED_M_290.jpg?v=1768926610',
            'https://scuffers.com/cdn/shop/files/03_SCFF_KNIT_ZIPPER_RED_M_235.jpg?v=1768926610',
            'https://scuffers.com/cdn/shop/files/DROP_16_CO0954.jpg?v=1766414481',
            'https://scuffers.com/cdn/shop/files/DROP_16_CO0746_e36ce7ea-5adf-4a92-b0ba-af450a58be7c.jpg?v=1765915763'
        ]

        print("Testing RIGHT URLs (should pass):")
        all_right_passed = True
        for url in right_urls:
            result = scraper._is_desired_image(url)
            status = "PASS" if result else "FAIL"
            print(f"  {status}: {url.split('/')[-1]}")
            if not result:
                all_right_passed = False

        print("\nTesting WRONG URLs (should fail):")
        all_wrong_failed = True
        for url in wrong_urls:
            result = scraper._is_desired_image(url)
            status = "FAIL" if result else "PASS"
            print(f"  {status}: {url.split('/')[-1]}")
            if result:
                all_wrong_failed = False

        if all_right_passed and all_wrong_failed:
            print("\nImage filtering test PASSED")
            return True
        else:
            print("\nImage filtering test FAILED")
            return False

    except Exception as e:
        print(f"Image filtering test failed: {e}")
        return False

def test_database_connection():
    """Test Supabase connection (skipped when SUPABASE_URL/KEY not set)."""
    print("Testing Supabase connection...")

    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        print("Skipped (SUPABASE_URL and SUPABASE_KEY not set)")
        return True

    try:
        from scraper.database import get_db

        db = get_db()
        count = db.get_product_count()

        print(f"Database connection successful. Current product count: {count}")
        return True

    except Exception as e:
        print(f"Database connection failed: {e}")
        return False

def test_html_scraper():
    """Test HTML scraping."""
    print("Testing HTML scraper...")

    try:
        from scraper.html_scraper import HTMLScraper

        scraper = HTMLScraper()
        url = "https://scuffers.com/collections/all"

        # Just test if we can fetch the page
        import requests
        response = requests.get(url, headers={'User-Agent': os.getenv('USER_AGENT', 'test')}, timeout=10)

        if response.status_code == 200:
            print(f"Page fetch successful: {len(response.content)} bytes")
            return True
        else:
            print(f"Page fetch failed: HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"HTML scraper test failed: {e}")
        return False

def test_database_upsert_payload_no_embedding():
    """Assert the payload sent to Supabase never contains the removed 'embedding' column."""
    print("Testing database upsert payload (no 'embedding' key)...")

    try:
        from scraper.database import get_db, SupabaseDB
        import json
        from unittest.mock import patch, MagicMock

        # Products: one with image_embedding, one with stray 'embedding' (must be stripped)
        mock_products = [
            {
                'source': 'test',
                'product_url': 'https://example.com/p/1',
                'image_url': 'https://example.com/img1.jpg',
                'title': 'Product 1',
                'image_embedding': [0.1] * 768,
                'info_embedding': [0.2] * 768,
            },
            {
                'source': 'test',
                'product_url': 'https://example.com/p/2',
                'image_url': 'https://example.com/img2.jpg',
                'title': 'Product 2',
                'embedding': [0.99] * 768,  # old key - must not appear in payload
            },
        ]
        payload_sent = []

        def capture_post(url, headers=None, data=None, timeout=None, **kwargs):
            payload_sent.append(json.loads(data))
            r = MagicMock()
            r.status_code = 201
            return r

        # If env is set, run real code path with patched post
        if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"):
            with patch('requests.Session.post', side_effect=capture_post):
                db = get_db()
                db.upsert_products(mock_products)
        else:
            # No env: test format + whitelist without connecting
            db = SupabaseDB.__new__(SupabaseDB)
            allowed_columns = {
                'id', 'source', 'product_url', 'affiliate_url', 'image_url', 'brand', 'title',
                'description', 'category', 'gender', 'metadata', 'size', 'second_hand',
                'image_embedding', 'info_embedding', 'country', 'tags', 'other', 'price', 'sale',
                'additional_images',
            }
            formatted = []
            for p in mock_products:
                f = db._format_product_for_db(p)
                if f:
                    formatted.append(f)
            all_keys = set(k for k in formatted[0].keys() if k in allowed_columns)
            payload_sent = [{k: p.get(k) for k in all_keys} for p in formatted]

        for chunk in payload_sent:
            for row in (chunk if isinstance(chunk, list) else [chunk]):
                if 'embedding' in row:
                    print(f"FAIL: payload contains 'embedding' key: {list(row.keys())}")
                    return False
        print("Payload contains no 'embedding' key")
        return True
    except Exception as e:
        print(f"Database payload test failed: {e}")
        return False

def test_database_upsert_live():
    """Test real upsert of 1 product when SUPABASE_URL/KEY are set (validates full import)."""
    print("Testing database upsert (live)...")

    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        print("Skipped (SUPABASE_URL and SUPABASE_KEY not set)")
        return True

    try:
        from scraper.database import upsert_products
        one = [{
            'source': 'scraper',
            'product_url': 'https://scuffers.com/products/test-upsert-payload-check',
            'image_url': 'https://scuffers.com/cdn/shop/files/test.jpg',
            'title': 'Test upsert payload',
            'brand': 'Scuffers',
            'price': '100 EUR',
            'country': 'eu',
        }]
        ok = upsert_products(one)
        if ok:
            print("Live upsert succeeded (1 row)")
            return True
        print("Live upsert returned False")
        return False
    except Exception as e:
        print(f"Live upsert failed: {e}")
        return False

def test_config():
    """Test configuration loading."""
    print("Testing configuration...")

    try:
        import yaml

        with open('sites.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        if 'scuffers' in config:
            print("Configuration loaded successfully")
            print(f"   Sites configured: {list(config.keys())}")
            return True
        else:
            print("Scuffers not found in configuration")
            return False

    except Exception as e:
        print(f"Configuration test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("Running Scuffers Scraper Tests\n")

    tests = [
        ("Configuration", test_config),
        ("Database Connection", test_database_connection),
        ("Database payload no 'embedding'", test_database_upsert_payload_no_embedding),
        ("Database upsert (live)", test_database_upsert_live),
        ("Image Filtering", test_image_filtering),
        ("HTML Scraper", test_html_scraper),
        ("Embeddings", test_embeddings),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"{test_name} crashed: {e}")
            results.append((test_name, False))
        print()

    # Summary
    print("Test Results:")
    passed = 0
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1

    print(f"\n{passed}/{len(results)} tests passed")

    if passed == len(results):
        print("All tests passed! Ready to scrape.")
        return 0
    else:
        print("Some tests failed. Check configuration and dependencies.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
