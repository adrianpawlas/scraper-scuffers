#!/usr/bin/env python3
"""
Command-line interface for the fashion scraper.
"""

import argparse
import logging
import sys
import os
from dotenv import load_dotenv

# Add parent directory to path so we can import scraper modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from scraper.scraper import FashionScraper
except ImportError:
    from scraper import FashionScraper

# Load environment variables
load_dotenv()

def setup_logging(level: str = 'INFO'):
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

def main():
    parser = argparse.ArgumentParser(description='Fashion Scraper CLI')
    parser.add_argument(
        '--sites',
        nargs='+',
        choices=['all', 'scuffers'],
        default=['all'],
        help='Sites to scrape (default: all)'
    )
    parser.add_argument(
        '--sync',
        action='store_true',
        default=False,
        help='Sync scraped data to database'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of products to scrape per site (for testing)'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Set logging level'
    )
    parser.add_argument(
        '--config',
        default='sites.yaml',
        help='Path to sites configuration file'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)

    logger = logging.getLogger(__name__)
    logger.info("Starting Fashion Scraper CLI")

    # Validate environment
    required_env_vars = ['SUPABASE_URL', 'SUPABASE_KEY']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_vars and args.sync:
        logger.error(f"Missing required environment variables for sync: {missing_vars}")
        logger.error("Please set SUPABASE_URL and SUPABASE_KEY in your .env file")
        sys.exit(1)

    if not os.getenv('EMBEDDINGS_MODEL'):
        logger.warning("EMBEDDINGS_MODEL not set, using default: google/siglip-large-patch16-384")

    try:
        # Initialize scraper
        scraper = FashionScraper(args.config)

        # Determine sites to scrape
        if 'all' in args.sites:
            sites_to_scrape = list(scraper.config.keys())
        else:
            sites_to_scrape = args.sites

        logger.info(f"Sites to scrape: {sites_to_scrape}")

        # Scrape sites
        success = True
        for site in sites_to_scrape:
            site_success = scraper.scrape_site(site, sync=args.sync, limit=args.limit)
            if not site_success:
                success = False
                logger.error(f"Failed to scrape site: {site}")

        if success:
            logger.info("All sites scraped successfully!")
            sys.exit(0)
        else:
            logger.error("Some sites failed to scrape")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Scraper interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
