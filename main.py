import logging
import time
import argparse
import json
from datetime import datetime
from scraper.category_scraper import CategoryScraper
from scraper.product_scraper import ProductScraper
from scraper.embeddings import get_image_embedding, get_text_embedding
from scraper.database import get_db
from config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ScuffersScraper:
    def __init__(self):
        logger.info("Initializing Scuffers Scraper")
        
        self.category_scraper = CategoryScraper()
        self.product_scraper = ProductScraper()
        self.db = get_db()
        
        # Stats
        self.new_count = 0
        self.updated_count = 0
        self.unchanged_count = 0
        self.deleted_count = 0
        self.failed_count = 0
        
        # Track products seen in this run
        self.seen_product_urls = set()
        
        # Cache for existing products
        self.existing_products = {}
    
    def load_existing_products(self):
        """Load existing products from database into memory for comparison."""
        logger.info("Loading existing products from database...")
        self.existing_products = self.db.get_products_by_source(config.SOURCE)
        logger.info(f"Loaded {len(self.existing_products)} existing products")
    
    def has_product_changed(self, old: dict, new: dict) -> bool:
        """Check if product data has changed."""
        fields_to_check = ['title', 'price', 'sale', 'image_url', 'description', 
                          'category', 'gender', 'size', 'additional_images']
        
        for field in fields_to_check:
            old_val = old.get(field)
            new_val = new.get(field)
            
            # Handle None vs empty string
            if old_val is None:
                old_val = ""
            if new_val is None:
                new_val = ""
            
            if str(old_val) != str(new_val):
                return True
        
        return False
    
    def scrape_and_process(self, url: str, generate_embeddings: bool = True) -> dict:
        """Scrape a single product and determine if it needs embedding regeneration."""
        try:
            product_data = self.product_scraper.scrape_product(url)
            if not product_data:
                return {"status": "failed", "reason": "scrape_failed"}
            
            if not product_data.get("title"):
                return {"status": "failed", "reason": "no_title"}
            
            product_url = product_data.get("product_url")
            self.seen_product_urls.add(product_url)
            
            # Check if product exists
            existing = self.existing_products.get(product_url)
            
            if existing:
                # Check if anything changed
                if not self.has_product_changed(existing, product_data):
                    # Nothing changed - skip entirely
                    return {"status": "unchanged", "product": existing}
                
                # Product changed - check if image URL changed
                image_changed = (existing.get("image_url") != product_data.get("image_url"))
                
                if not generate_embeddings:
                    # Skip embeddings - just update data
                    product_data["image_embedding"] = existing.get("image_embedding")
                    product_data["info_embedding"] = existing.get("info_embedding")
                elif image_changed:
                    # Image changed - regenerate both embeddings
                    product_data = self._add_embeddings(product_data)
                else:
                    # No image change - keep existing image embedding, regenerate text
                    product_data["image_embedding"] = existing.get("image_embedding")
                    product_data = self._add_text_embedding_only(product_data)
                
                return {"status": "updated", "product": product_data}
            else:
                # New product - generate embeddings
                if generate_embeddings:
                    product_data = self._add_embeddings(product_data)
                
                return {"status": "new", "product": product_data}
            
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            return {"status": "failed", "reason": str(e)}
    
    def _add_embeddings(self, product_data: dict) -> dict:
        """Add both image and text embeddings."""
        image_url = product_data.get("image_url")
        if image_url:
            time.sleep(0.5)  # Stagger API calls
            image_embedding = get_image_embedding(image_url)
            product_data["image_embedding"] = image_embedding
        
        time.sleep(0.5)  # Stagger API calls
        combined_text = self._generate_combined_text(product_data)
        info_embedding = get_text_embedding(combined_text)
        product_data["info_embedding"] = info_embedding
        
        return product_data
    
    def _add_text_embedding_only(self, product_data: dict) -> dict:
        """Add only text embedding (for updated products without image change)."""
        time.sleep(0.5)  # Stagger API calls
        combined_text = self._generate_combined_text(product_data)
        info_embedding = get_text_embedding(combined_text)
        product_data["info_embedding"] = info_embedding
        return product_data
    
    def _generate_combined_text(self, product_data: dict) -> str:
        parts = []
        
        if product_data.get("title"):
            parts.append(f"Title: {product_data['title']}")
        if product_data.get("brand"):
            parts.append(f"Brand: {product_data['brand']}")
        if product_data.get("description"):
            parts.append(f"Description: {product_data['description']}")
        if product_data.get("category"):
            parts.append(f"Category: {product_data['category']}")
        if product_data.get("gender"):
            parts.append(f"Gender: {product_data['gender']}")
        if product_data.get("price"):
            parts.append(f"Price: {product_data['price']}")
        if product_data.get("size"):
            parts.append(f"Sizes: {product_data['size']}")
        if product_data.get("metadata"):
            parts.append(f"Details: {product_data['metadata']}")
        
        return " | ".join(parts)
    
    def process_batch(self, urls: list, batch_size: int = 50) -> list:
        """Process products in batches with smart upsert logic."""
        batch = []
        
        for url in urls:
            result = self.scrape_and_process(url)
            
            if result["status"] == "new":
                self.new_count += 1
                batch.append(result["product"])
                
            elif result["status"] == "updated":
                self.updated_count += 1
                batch.append(result["product"])
                
            elif result["status"] == "unchanged":
                self.unchanged_count += 1
                
            elif result["status"] == "failed":
                self.failed_count += 1
            
            # Insert batch when full
            if len(batch) >= batch_size:
                self._upsert_batch(batch)
                batch = []
        
        # Insert remaining
        if batch:
            self._upsert_batch(batch)
        
        return batch
    
    def _upsert_batch(self, products: list, max_retries: int = 3) -> bool:
        """Upsert a batch of products with retry logic."""
        for attempt in range(max_retries):
            try:
                success = self.db.upsert_products_batch(products)
                if success:
                    return True
                logger.warning(f"Batch upsert returned failure, attempt {attempt + 1}/{max_retries}")
            except Exception as e:
                logger.warning(f"Batch upsert failed: {e}, attempt {attempt + 1}/{max_retries}")
                time.sleep(2)
        
        # All retries failed - log to file
        self._log_failed_products(products)
        return False
    
    def _log_failed_products(self, products: list):
        """Log failed products to a file."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"failed_products_{timestamp}.json"
            with open(filename, 'w') as f:
                json.dump(products, f, indent=2)
            logger.error(f"Logged {len(products)} failed products to {filename}")
        except Exception as e:
            logger.error(f"Failed to log error file: {e}")
    
    def cleanup_stale_products(self):
        """Remove products not seen in current scrape run."""
        logger.info("Checking for stale products...")
        
        stale_products = []
        for product_url, product_data in self.existing_products.items():
            if product_url not in self.seen_product_urls:
                # Product not seen in this run - check consecutive misses
                last_seen_run = product_data.get("last_seen_run", 0)
                current_run = getattr(self, 'run_number', 1)
                
                # If missed for 2 consecutive runs, mark for deletion
                if current_run - last_seen_run >= 2:
                    stale_products.append(product_data)
        
        if stale_products:
            logger.info(f"Found {len(stale_products)} stale products to remove")
            deleted = self.db.delete_products(stale_products)
            self.deleted_count = deleted
            logger.info(f"Deleted {deleted} stale products")
        else:
            logger.info("No stale products found")
    
    def update_last_seen_runs(self):
        """Update last_seen_run for products seen in this run."""
        products_to_update = []
        
        for product_url in self.seen_product_urls:
            if product_url in self.existing_products:
                product = self.existing_products[product_url].copy()
                product["last_seen_run"] = getattr(self, 'run_number', 1)
                products_to_update.append(product)
        
        if products_to_update:
            self.db.upsert_products_batch(products_to_update)
    
    def run(self, test_mode: bool = False, max_products: int = None):
        logger.info("=" * 60)
        logger.info("Starting Scuffers Scraper")
        logger.info("=" * 60)
        
        start_time = time.time()
        
        # Load existing products
        self.load_existing_products()
        
        # Scrape URLs
        logger.info("Step 1: Scraping category pages for product URLs")
        product_urls = self.category_scraper.scrape_all_categories()
        logger.info(f"Found {len(product_urls)} unique product URLs")
        
        if test_mode:
            product_urls = product_urls[:3]
            logger.info(f"Test mode: limiting to {len(product_urls)} products")
        
        if max_products:
            product_urls = product_urls[:max_products]
            logger.info(f"Limited to {len(product_urls)} products")
        
        # Process products in batches
        logger.info(f"Step 2: Processing {len(product_urls)} products")
        self.process_batch(product_urls, batch_size=50)
        
        # Update last seen runs
        self.update_last_seen_runs()
        
        # Cleanup stale products
        self.cleanup_stale_products()
        
        elapsed_time = time.time() - start_time
        
        # Print summary
        logger.info("=" * 60)
        logger.info("Scraping Complete!")
        logger.info(f"  New products added: {self.new_count}")
        logger.info(f"  Products updated: {self.updated_count}")
        logger.info(f"  Products unchanged (skipped): {self.unchanged_count}")
        logger.info(f"  Stale products deleted: {self.deleted_count}")
        logger.info(f"  Failed: {self.failed_count}")
        logger.info(f"  Time elapsed: {elapsed_time:.2f} seconds")
        logger.info("=" * 60)
    
    def scrape_single_product(self, url: str):
        logger.info(f"Single product mode: {url}")
        self.load_existing_products()
        
        result = self.scrape_and_process(url)
        
        if result["status"] in ["new", "updated"]:
            self.db.upsert_products_batch([result["product"]])
            logger.info(f"Successfully saved: {result['product'].get('title')}")
        elif result["status"] == "unchanged":
            logger.info("Product unchanged, no update needed")
        else:
            logger.error(f"Failed: {result.get('reason')}")


def main():
    parser = argparse.ArgumentParser(description="Scuffers Scraper")
    parser.add_argument("--test", action="store_true", help="Run in test mode (3 products)")
    parser.add_argument("--max", type=int, default=None, help="Maximum number of products to scrape")
    parser.add_argument("--url", type=str, help="Scrape a single product URL")
    
    args = parser.parse_args()
    
    scraper = ScuffersScraper()
    
    if args.url:
        scraper.scrape_single_product(args.url)
    else:
        scraper.run(test_mode=args.test, max_products=args.max)


if __name__ == "__main__":
    main()
