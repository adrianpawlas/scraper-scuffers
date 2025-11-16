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
    from .browser_scraper import BrowserScraper
    from .embeddings import get_batch_embeddings
    from .database import upsert_products
except ImportError:
    from html_scraper import HTMLScraper
    from browser_scraper import BrowserScraper
    from embeddings import get_batch_embeddings
    from database import upsert_products

logger = logging.getLogger(__name__)

class FashionScraper:
    def __init__(self, config_path: str = 'sites.yaml'):
        self.config = self._load_config(config_path)
        self.user_agent = os.getenv('USER_AGENT', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        self.html_scraper = HTMLScraper(user_agent=self.user_agent, delay=2.0)
        self.browser_scraper = None  # Will be initialized when needed

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
        # Run the async version in a new event loop
        import asyncio
        try:
            return asyncio.run(self.scrape_site_async(site_name, sync, limit))
        except RuntimeError:
            # If already in an event loop, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.scrape_site_async(site_name, sync, limit))
            finally:
                loop.close()

    async def scrape_site_async(self, site_name: str, sync: bool = True, limit: Optional[int] = None) -> bool:
        """
        Async version of scrape_site for browser scraping.

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
                mode = site_config.get('mode', 'html')
                if mode == 'browser':
                    # Use browser scraper for dynamic content
                    logger.info("Using browser scraper for dynamic content loading")
                    listings = await self._scrape_with_browser(category_url, site_config)
                else:
                    # Use HTML scraper for static content
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
                        logger.debug(f"Scraping product page: {product_url}")

                        # Try to scrape individual product page with retry logic
                        product_data = None
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                product_data = self.html_scraper.scrape_product_page(
                                    product_url,
                                    site_config.get('selectors', {}),
                                    site_config
                                )
                                if product_data:
                                    break
                            except Exception as e:
                                logger.warning(f"Attempt {attempt + 1} failed for {product_url}: {e}")
                                if attempt < max_retries - 1:
                                    import time
                                    time.sleep(2 * (attempt + 1))  # Exponential backoff

                        if product_data:
                            # Merge listing data with detailed product data
                            # Use listing data as base, then update with detailed data
                            merged_product = dict(listing)  # Start with listing data
                            merged_product.update(product_data)  # Override with detailed data

                            # Generate embedding if image URL is available
                            image_url = merged_product.get('image_url')
                            if image_url:
                                logger.debug(f"Generating embedding for {product_url}")
                                try:
                                    embedding = get_batch_embeddings([image_url])[0]
                                    if embedding:
                                        merged_product['embedding'] = embedding
                                        logger.debug(f"Generated embedding with {len(embedding)} dimensions")
                                    else:
                                        logger.warning(f"Failed to generate embedding for {product_url}")
                                except Exception as e:
                                    logger.error(f"Error generating embedding for {product_url}: {e}")

                            products.append(merged_product)
                        else:
                            # If detailed scraping failed, still include the basic listing data
                            logger.warning(f"Detailed scraping failed for {product_url}, using basic listing data")
                            basic_product = dict(listing)
                            basic_product.update({
                                'source': site_config.get('source'),
                                'brand': site_config.get('brand'),
                                'second_hand': site_config.get('second_hand', False),
                                'currency': site_config.get('currency', 'EUR'),
                                # Store additional metadata
                                'merchant_name': site_config.get('merchant_name'),
                                'country': site_config.get('country', 'eu'),
                            })
                            products.append(basic_product)

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

    async def _scrape_with_browser(self, url: str, site_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Scrape products using browser automation for dynamic content.

        Args:
            url: Category URL to scrape
            site_config: Site configuration

        Returns:
            List of product listings
        """
        if not self.browser_scraper:
            self.browser_scraper = BrowserScraper(user_agent=self.user_agent)

        max_products = 1500  # Higher limit for browser scraping
        products = await self.browser_scraper.scrape_all_products(
            url,
            site_config.get('selectors', {}),
            max_products=max_products
        )

        logger.info(f"Browser scraper found {len(products)} products")
        return products

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
