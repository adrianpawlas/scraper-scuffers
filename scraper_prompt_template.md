# Universal Fashion Scraper Builder Prompt

You are an expert Python developer specializing in web scraping, browser automation, and database integration. Your task is to build a comprehensive fashion product scraper that can work with multiple brands and integrate with Supabase and AI embeddings.

## Project Requirements

### Brand Configuration
- **Brand Name**: `{BRAND_NAME}`
- **Category URL**: `{CATEGORY_URL}` (e.g., https://brand.com/collections/all)
- **Product URL Pattern**: `{PRODUCT_URL_PATTERN}` (e.g., https://brand.com/products/{product-slug})

### Database Schema (Supabase)
```sql
CREATE TABLE products (
  id text not null PRIMARY KEY,
  source text null,
  product_url text null,
  affiliate_url text null,
  image_url text not null,
  brand text null,
  title text not null,
  description text null,
  category text null,
  gender text null,
  price double precision null,
  currency text null,
  search_tsv tsvector null,
  created_at timestamp with time zone null default now(),
  metadata text null,
  size text null,
  second_hand boolean null default false,
  embedding public.vector null
);
```

### Embedding Configuration
- **Model**: `{EMBEDDING_MODEL}` (e.g., google/siglip-base-patch16-384)
- **Dimensions**: `{EMBEDDING_DIMENSIONS}` (e.g., 768)
- **Device**: Auto-detect (CPU/CUDA)

## Technical Requirements

### 1. Core Architecture
Build a modular scraper with these components:
- **HTML Scraper**: Static content parsing
- **Browser Scraper**: Dynamic content with Playwright
- **Database Layer**: Supabase integration
- **Embedding Layer**: AI-powered image embeddings
- **Configuration Management**: YAML-based brand configs
- **Logging & Monitoring**: Comprehensive logging

### 2. Scraping Strategy
- **Category Page**: Extract product listings
- **Product Pages**: Detailed product information
- **Dynamic Content**: Handle pagination, infinite scroll, lazy loading
- **Error Handling**: Robust retry logic and error recovery
- **Rate Limiting**: Respectful scraping with delays

### 3. Data Processing
- **ID Generation**: Create unique IDs using `hashlib.md5(f"{source}:{product_url}".encode()).hexdigest()[:16]`
- **Required Fields**: `source`, `product_url`, `image_url`, `title`
- **Optional Fields**: `affiliate_url`, `description`, `category`, `gender`, `price`, `currency`, `size`, `brand`
- **Metadata**: Store additional info as JSON in `metadata` field
- **Embedding Generation**: Process images through SigLIP model

## Implementation Instructions

### Step 1: Project Structure
```
scraper/
├── __init__.py
├── cli.py                    # Command-line interface
├── config.py                 # Configuration management
├── database.py              # Supabase operations
├── embeddings.py            # AI embeddings
├── html_scraper.py          # Static content scraper
├── browser_scraper.py       # Dynamic content scraper
├── scraper.py               # Main scraper orchestration
└── utils.py                 # Helper functions

sites/
└── {brand_name}.yaml        # Brand-specific configuration
```

### Step 2: Brand Configuration Format
Create a YAML configuration file for each brand:

```yaml
source: "{brand_name}"
merchant_name: "{Brand Name}"
brand: "{Brand Name}"
url: "{CATEGORY_URL}"
mode: "browser"  # or "html"
second_hand: false
country: "eu"
currency: "EUR"

selectors:
  # Category page selectors
  category:
    container: "{CSS_SELECTOR}"
    product: "{CSS_SELECTOR}"
    product_url: "{CSS_SELECTOR}"
    image_url: "{CSS_SELECTOR}"
    title: "{CSS_SELECTOR}"
    price: "{CSS_SELECTOR}"

  # Product page selectors
  product:
    title: "{CSS_SELECTOR}"
    description: "{CSS_SELECTOR}"
    images: "{CSS_SELECTOR}"
    price: "{CSS_SELECTOR}"
    category: "{CSS_SELECTOR}"
    gender: "{CSS_SELECTOR}"
    size: "{CSS_SELECTOR}"

# Pagination settings
pagination:
  type: "button"  # or "infinite_scroll" or "url_based"
  load_more_selector: "{CSS_SELECTOR}"
  next_page_selector: "{CSS_SELECTOR}"
  max_pages: 50

# Browser settings
browser:
  headless: true
  user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
  viewport: {width: 1920, height: 1080}
```

### Step 3: Core Components Implementation

#### Database Layer (`database.py`)
```python
import os
import logging
from typing import Dict, List, Any, Optional
from supabase import create_client, Client
import json
import hashlib

class SupabaseDB:
    def upsert_products(self, products: List[Dict[str, Any]]) -> bool:
        # Implement upsert with conflict resolution on 'id'
        # Handle metadata as JSON
        # Batch operations for performance

    def _format_product_for_db(self, product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Generate unique ID: f"{source}_{hash}"
        # Validate required fields
        # Convert metadata to JSON
        # Handle embedding field
```

#### Embedding Layer (`embeddings.py`)
```python
from transformers import SiglipProcessor, SiglipModel
import torch
from PIL import Image
import requests

class SigLIPEmbeddings:
    def __init__(self, model_name: str = "{EMBEDDING_MODEL}"):
        # Load SigLIP model and processor
        # Set up device (CPU/CUDA)

    def get_image_embedding(self, image_url: str) -> Optional[List[float]]:
        # Download image
        # Process with SigLIP (requires both text and image inputs)
        # Return {EMBEDDING_DIMENSIONS}-dimensional vector
```

#### Browser Scraper (`browser_scraper.py`)
```python
from playwright.async_api import async_playwright
import asyncio

class BrowserScraper:
    async def scrape_all_products(self, url: str, selectors: Dict, max_products: int = 1000):
        # Launch browser
        # Navigate to category page
        # Handle pagination (Load More button, infinite scroll, etc.)
        # Extract product data
        # Return product listings

    async def _handle_pagination(self, page, pagination_config: Dict):
        # Implement different pagination strategies
        # Button clicking with retry logic
        # Scroll-based loading
        # URL-based pagination
```

### Step 4: Error Handling & Robustness

#### Retry Logic
```python
async def scrape_with_retry(self, url: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return await self.scrape_product_page(url)
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"Failed after {max_retries} attempts: {url}")
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

#### Logging
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
```

### Step 5: CLI Interface (`cli.py`)
```python
import argparse
from scraper import FashionScraper

def main():
    parser = argparse.ArgumentParser(description='Fashion Product Scraper')
    parser.add_argument('--sites', help='Comma-separated list of sites to scrape')
    parser.add_argument('--sync', action='store_true', help='Sync to database')
    parser.add_argument('--limit', type=int, help='Limit products per site')

    args = parser.parse_args()

    scraper = FashionScraper()

    if args.sites:
        sites = args.sites.split(',')
        for site in sites:
            scraper.scrape_site(site, sync=args.sync, limit=args.limit)
    else:
        scraper.scrape_all_sites(sync=args.sync, limit=args.limit)
```

## Key Technical Details

### SigLIP Model Requirements
- **Input**: Both text and image required for processing
- **Text Input**: Use empty string `""` for image-only embeddings
- **Output**: Normalized {EMBEDDING_DIMENSIONS}-dimensional vectors
- **Processing**: Batch processing for efficiency

### Database Operations
- **Upsert**: Use `on_conflict='id'` for conflict resolution
- **Batching**: Process in batches of 50 for performance
- **Unique IDs**: Generated from `source + product_url` hash
- **Metadata**: JSON-encoded additional information

### Browser Automation
- **Playwright**: Use for dynamic content
- **Headless Mode**: Default for production
- **User Agent**: Realistic browser fingerprinting
- **Timeouts**: Appropriate waiting times for page loads

### Pagination Strategies
1. **Button-based**: Click "Load More" buttons
2. **Infinite Scroll**: Scroll down with JavaScript
3. **URL-based**: Navigate through page URLs

## Quality Assurance

### Testing Requirements
- Unit tests for each component
- Integration tests with mock data
- End-to-end tests with real websites (with permission)
- Performance testing for large catalogs

### Monitoring & Maintenance
- Comprehensive logging at all levels
- Error tracking and alerting
- Performance metrics (products/second, success rates)
- Regular updates for website changes

## Deployment

### Environment Variables
```
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
EMBEDDINGS_MODEL={EMBEDDING_MODEL}
```

### Docker Configuration
```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium

COPY . .
CMD ["python", "-m", "scraper.cli", "--sites", "{BRAND_NAME}", "--sync"]
```

## Success Criteria

The scraper should:
1. ✅ Extract all products from category pages
2. ✅ Handle dynamic content and pagination
3. ✅ Generate high-quality embeddings
4. ✅ Store data correctly in Supabase
5. ✅ Handle errors gracefully
6. ✅ Be maintainable and extensible
7. ✅ Respect website terms and rate limits

## Next Steps

1. Analyze target website structure
2. Create brand-specific YAML configuration
3. Implement and test each component
4. Set up monitoring and alerting
5. Deploy and monitor performance
