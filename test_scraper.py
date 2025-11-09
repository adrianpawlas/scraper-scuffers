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
    """Test embedding generation."""
    print("Testing SigLIP embeddings...")

    try:
        from scraper.embeddings import get_image_embedding

        # Test with a sample image
        test_url = 'https://images.unsplash.com/photo-1523381210434-271e8be1f52b?w=400'
        embedding = get_image_embedding(test_url)

        if embedding and len(embedding) == 1024:
            print(f"✅ Embedding generation successful: {len(embedding)} dimensions")
            print(f"   First 5 values: {embedding[:5]}")
            return True
        else:
            print("❌ Embedding generation failed or wrong dimensions")
            return False

    except Exception as e:
        print(f"❌ Embedding test failed: {e}")
        return False

def test_database_connection():
    """Test Supabase connection."""
    print("Testing Supabase connection...")

    try:
        from scraper.database import get_db

        db = get_db()
        count = db.get_product_count()

        print(f"✅ Database connection successful. Current product count: {count}")
        return True

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
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
            print(f"✅ Page fetch successful: {len(response.content)} bytes")
            return True
        else:
            print(f"❌ Page fetch failed: HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ HTML scraper test failed: {e}")
        return False

def test_config():
    """Test configuration loading."""
    print("Testing configuration...")

    try:
        import yaml

        with open('sites.yaml', 'r') as f:
            config = yaml.safe_load(f)

        if 'scuffers' in config:
            print("✅ Configuration loaded successfully")
            print(f"   Sites configured: {list(config.keys())}")
            return True
        else:
            print("❌ Scuffers not found in configuration")
            return False

    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🧪 Running Scuffers Scraper Tests\n")

    tests = [
        ("Configuration", test_config),
        ("Database Connection", test_database_connection),
        ("HTML Scraper", test_html_scraper),
        ("Embeddings", test_embeddings),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))
        print()

    # Summary
    print("📊 Test Results:")
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1

    print(f"\n{passed}/{len(results)} tests passed")

    if passed == len(results):
        print("🎉 All tests passed! Ready to scrape.")
        return 0
    else:
        print("⚠️  Some tests failed. Check configuration and dependencies.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
