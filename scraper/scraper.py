"""
Main scraper module for fashion brands.
Coordinates HTML scraping, embedding generation, and database operations.
"""

import logging
import time
from typing import Dict, List, Any, Optional
import yaml
import os

try:
    from .html_scraper import HTMLScraper
    from .embeddings import get_batch_embeddings
    from .database import upsert_products
except ImportError:
    from html_scraper import HTMLScraper
    from embeddings import get_batch_embeddings
    from database import upsert_products

logger = logging.getLogger(__name__)

class FashionScraper:
    def __init__(self, config_path: str = 'sites.yaml'):
        self.config = self._load_config(config_path)
        self.user_agent = os.getenv('USER_AGENT', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        self.html_scraper = HTMLScraper(user_agent=self.user_agent, delay=1.0)

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load scraper configuration from YAML file."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            return {}

    def scrape_site(self, site_name: str, sync: bool = True, limit: Optional[int] = None) -> bool:
        """
        Scrape a specific site.

        Args:
            site_name: Name of the site to scrape (key in config)
            sync: Whether to sync to database
            limit: Maximum number of products to scrape (for testing)

        Returns:
            True if successful
        """
        if site_name not in self.config:
            logger.error(f"Site '{site_name}' not found in config")
            return False

        site_config = self.config[site_name]
        logger.info(f"Starting scrape for {site_name}")

        try:
            products = []

            # Scrape each category
            for category in site_config.get('categories', []):
                category_url = category['url']
                category_name = category.get('name', category_url)

                logger.info(f"Scraping category: {category_name}")

                # Get product listings from category page
                listings = self.html_scraper.scrape_category_page(
                    category_url,
                    site_config.get('selectors', {})
                )

                if limit:
                    listings = listings[:limit]

                # Scrape individual product pages
                for listing in listings:
                    product_url = listing.get('product_url')
                    if product_url:
                        product_data = self.html_scraper.scrape_product_page(
                            product_url,
                            site_config.get('selectors', {}),
                            site_config
                        )

                        if product_data:
                            # Merge listing data with detailed product data
                            product_data.update(listing)

                            # Generate embedding if image URL is available
                            image_url = product_data.get('image_url')
                            if image_url:
                                logger.debug(f"Generating embedding for {product_url}")
                                try:
                                    embedding = get_batch_embeddings([image_url])[0]
                                    if embedding:
                                        product_data['embedding'] = embedding
                                        logger.debug(f"Generated embedding with {len(embedding)} dimensions")
                                    else:
                                        logger.warning(f"Failed to generate embedding for {product_url}")
                                except Exception as e:
                                    logger.error(f"Error generating embedding for {product_url}: {e}")

                            products.append(product_data)

                            # Log progress
                            if len(products) % 10 == 0:
                                logger.info(f"Processed {len(products)} products so far")

            if not products:
                logger.warning(f"No products found for {site_name}")
                return False

            logger.info(f"Successfully scraped {len(products)} products from {site_name}")

            # Sync to database if requested
            if sync:
                logger.info("Syncing products to database...")
                success = upsert_products(products)
                if success:
                    logger.info("Successfully synced products to database")
                else:
                    logger.error("Failed to sync products to database")
                    return False

            return True

        except Exception as e:
            logger.error(f"Failed to scrape site {site_name}: {e}")
            return False

    def scrape_all_sites(self, sync: bool = True, limit: Optional[int] = None) -> bool:
        """
        Scrape all configured sites.

        Args:
            sync: Whether to sync to database
            limit: Maximum products per site (for testing)

        Returns:
            True if all sites scraped successfully
        """
        success = True

        for site_name in self.config.keys():
            site_success = self.scrape_site(site_name, sync=sync, limit=limit)
            if not site_success:
                success = False
                logger.error(f"Failed to scrape site: {site_name}")

        return success

    def get_site_config(self, site_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific site."""
        return self.config.get(site_name)
