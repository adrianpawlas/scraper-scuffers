# AI Fashion Scraper

Lightweight scraper for fashion brands that populates a Supabase products table with local SigLIP embeddings.

## Features

- **HTML Scraping**: Extracts product data from fashion websites
- **Local Embeddings**: Uses SigLIP model for high-quality image embeddings (1024 dimensions)
- **Supabase Integration**: Direct upsert to your database
- **Configurable**: YAML-based site configuration
- **Respectful Crawling**: Built-in delays and user-agent rotation

## Setup

### Prerequisites

- Python 3.11+
- Supabase account and project

### Installation

1. Clone this repository:
```bash
git clone <your-repo-url>
cd scraper-scuffers
```

2. Create virtual environment:
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Copy environment configuration:
```bash
cp .env.example .env
```

5. Edit `.env` with your values:
```env
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_service_role_key
USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
EMBEDDINGS_MODEL=google/siglip-large-patch16-384
```

### Database Setup

1. In your Supabase SQL editor, run:
```sql
-- Execute the schema
\i supabase_schema.sql

-- Run migration if needed
\i migrations/20251003_add_unique_index.sql
```

## Configuration

Edit `sites.yaml` to configure scraping targets. Example for Scuffers:

```yaml
scuffers:
  name: Scuffers
  source: scuffers
  mode: html
  base_url: https://scuffers.com
  categories:
    - url: https://scuffers.com/collections/all
      name: All Products
  selectors:
    products: ".product-item, .grid-item"
    product_url: "a[href*='/products/']"
    title: "h1, .product-title"
    price: ".price, [data-price]"
    image_url: "img"
    sizes: ".size-option, [data-size]"
  merchant_name: Scuffers
  brand: Scuffers
  second_hand: false
  country: eu
```

## Usage

### Basic Scraping

Scrape all configured sites and sync to database:
```bash
python -m scraper.cli --sites all --sync
```

Scrape specific site:
```bash
python -m scraper.cli --sites scuffers --sync
```

### Testing (Limited Products)

Test with limited products:
```bash
python -m scraper.cli --sites scuffers --sync --limit 5
```

### Embedding Testing

Test embedding generation:
```bash
python -c "
from scraper.embeddings import get_image_embedding
result = get_image_embedding('https://images.unsplash.com/photo-1523381210434-271e8be1f52b?w=400')
print(f'Success: {len(result) == 1024}' if result else 'Failed')
"
```

## Data Schema

Products are stored with these fields:

- `source`: Scraper source identifier
- `external_id`: Unique product identifier
- `merchant_name`: "Scuffers"
- `product_url`: Full product page URL
- `image_url`: Primary product image URL
- `brand`: "Scuffers"
- `title`: Product title/name
- `gender`: "men" or "women" (inferred)
- `price`: Numeric price value
- `currency`: "EUR"
- `size`: Available sizes (comma-separated)
- `second_hand`: false
- `embedding`: 1024-dimensional SigLIP vector
- `country`: "eu"

## Legal & Ethics

- Respects robots.txt
- Uses realistic User-Agent strings
- Includes delays between requests
- Only scrapes public product data

## Scheduling

### GitHub Actions

1. Add secrets to your repository:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `USER_AGENT`
   - `EMBEDDINGS_MODEL`

2. The workflow runs daily at 2 AM UTC automatically.

### Manual Scheduling

Use cron or task scheduler to run:
```bash
python -m scraper.cli --sites all --sync
```

## Troubleshooting

### Common Issues

1. **Embedding generation fails**: Check internet connection and image URLs
2. **Database connection fails**: Verify Supabase credentials
3. **No products found**: Check selectors in `sites.yaml`

### Logs

Run with debug logging:
```bash
python -m scraper.cli --sites scuffers --sync --log-level DEBUG
```

## Architecture

- `scraper/scraper.py`: Main coordination logic
- `scraper/html_scraper.py`: HTML parsing and extraction
- `scraper/embeddings.py`: SigLIP model for image embeddings
- `scraper/database.py`: Supabase operations
- `scraper/cli.py`: Command-line interface
- `sites.yaml`: Site configurations
