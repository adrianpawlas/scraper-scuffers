import logging
import time
import argparse
from scraper.category_scraper import CategoryScraper
from scraper.product_scraper import ProductScraper
from scraper.embeddings import get_image_embedding, get_text_embedding
from scraper.database import upsert_products
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
        
        self.scraped_count = 0
        self.failed_count = 0
        self.inserted_count = 0
    
    def process_product(self, url: str) -> bool:
        try:
            product_data = self.product_scraper.scrape_product(url)
            if not product_data:
                logger.warning(f"Failed to scrape product: {url}")
                self.failed_count += 1
                return False
            
            if not product_data.get("title"):
                logger.warning(f"Product has no title: {url}")
                self.failed_count += 1
                return False
            
            logger.info(f"Processing: {product_data['title']}")
            
            image_url = product_data.get("image_url")
            image_embedding = None
            if image_url:
                logger.info(f"Generating image embedding for: {image_url}")
                image_embedding = get_image_embedding(image_url)
                if image_embedding:
                    logger.info(f"Image embedding generated successfully ({len(image_embedding)} dims)")
            
            combined_text = self._generate_combined_text(product_data)
            info_embedding = get_text_embedding(combined_text)
            if info_embedding:
                logger.info(f"Info embedding generated successfully ({len(info_embedding)} dims)")
            
            product_data["image_embedding"] = image_embedding
            product_data["info_embedding"] = info_embedding
            
            success = upsert_products([product_data])
            
            if success:
                self.inserted_count += 1
                logger.info(f"Successfully processed: {product_data['title']}")
            else:
                self.failed_count += 1
            
            self.scraped_count += 1
            return success
            
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            self.failed_count += 1
            return False
    
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
    
    def run(self, test_mode: bool = False, max_products: int = None):
        logger.info("=" * 60)
        logger.info("Starting Scuffers Scraper")
        logger.info("=" * 60)
        
        start_time = time.time()
        
        logger.info("Step 1: Scraping category pages for product URLs")
        product_urls = self.category_scraper.scrape_all_categories()
        logger.info(f"Found {len(product_urls)} unique product URLs")
        
        if test_mode:
            product_urls = product_urls[:3]
            logger.info(f"Test mode: limiting to {len(product_urls)} products")
        
        if max_products:
            product_urls = product_urls[:max_products]
            logger.info(f"Limited to {len(product_urls)} products")
        
        logger.info(f"Step 2: Scraping {len(product_urls)} products")
        for i, url in enumerate(product_urls, 1):
            logger.info(f"Processing product {i}/{len(product_urls)}")
            self.process_product(url)
            
            if i < len(product_urls):
                time.sleep(config.DELAY_BETWEEN_REQUESTS)
        
        elapsed_time = time.time() - start_time
        
        logger.info("=" * 60)
        logger.info("Scraping Complete!")
        logger.info(f"Total products scraped: {self.scraped_count}")
        logger.info(f"Successfully inserted: {self.inserted_count}")
        logger.info(f"Failed: {self.failed_count}")
        logger.info(f"Time elapsed: {elapsed_time:.2f} seconds")
        logger.info("=" * 60)
    
    def scrape_single_product(self, url: str):
        logger.info(f"Single product mode: {url}")
        self.process_product(url)


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
