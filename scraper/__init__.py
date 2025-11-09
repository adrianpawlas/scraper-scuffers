"""
Fashion Scraper Package
"""

try:
    from .scraper import FashionScraper
    from .html_scraper import HTMLScraper
    from .embeddings import get_image_embedding, get_batch_embeddings
    from .database import upsert_products, get_db
except ImportError:
    # Allow imports when run as script
    pass

__version__ = "1.0.0"
