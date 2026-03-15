import requests
from bs4 import BeautifulSoup
import time
import logging
from typing import List, Set
from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CategoryScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
        self.product_urls: Set[str] = set()
    
    def get_page(self, url: str) -> BeautifulSoup:
        for attempt in range(config.MAX_RETRIES):
            try:
                response = self.session.get(url, timeout=config.TIMEOUT)
                response.raise_for_status()
                return BeautifulSoup(response.text, "lxml")
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < config.MAX_RETRIES - 1:
                    time.sleep(config.DELAY_BETWEEN_REQUESTS * (attempt + 1))
                else:
                    raise
        return None
    
    def extract_product_links(self, soup: BeautifulSoup) -> List[str]:
        links = []
        
        product_cards = soup.select("div.product-card a[href*='/products/']")
        for card in product_cards:
            href = card.get("href", "")
            if href and "/products/" in href:
                full_url = href if href.startswith("http") else f"{config.BASE_URL}{href}"
                links.append(full_url)
        
        product_items = soup.select("li.grid__item a[href*='/products/']")
        for item in product_items:
            href = item.get("href", "")
            if href and "/products/" in href:
                full_url = href if href.startswith("http") else f"{config.BASE_URL}{href}"
                links.append(full_url)
        
        product_links = soup.select("a[href*='/products/']")
        for link in product_links:
            href = link.get("href", "")
            if href and "/products/" in href and "quick-view" not in href.lower():
                full_url = href if href.startswith("http") else f"{config.BASE_URL}{href}"
                links.append(full_url)
        
        return list(set(links))
    
    def get_next_page_url(self, soup: BeautifulSoup) -> str:
        load_more = soup.select_one("button#load-more")
        if load_more:
            next_url = load_more.get("data-next-url")
            if next_url:
                return f"{config.BASE_URL}{next_url}"
        
        pagination = soup.select_one("button.load-more")
        if pagination:
            next_url = pagination.get("data-next-url")
            if next_url:
                return f"{config.BASE_URL}{next_url}"
        
        next_link = soup.select_one("a[rel='next']")
        if next_link:
            return next_link.get("href", "")
        
        return None
    
    def scrape_category(self, category_url: str, max_pages: int = None) -> List[str]:
        logger.info(f"Scraping category: {category_url}")
        current_url = category_url
        page_count = 0
        
        while current_url:
            page_count += 1
            if max_pages and page_count > max_pages:
                logger.info(f"Reached max pages limit: {max_pages}")
                break
            
            logger.info(f"Scraping page {page_count}: {current_url}")
            
            soup = self.get_page(current_url)
            if not soup:
                break
            
            product_links = self.extract_product_links(soup)
            new_links = [link for link in product_links if link not in self.product_urls]
            self.product_urls.update(new_links)
            logger.info(f"Found {len(new_links)} new product URLs (total: {len(self.product_urls)})")
            
            next_url = self.get_next_page_url(soup)
            if next_url and next_url != current_url:
                current_url = next_url
                time.sleep(config.DELAY_BETWEEN_REQUESTS)
            else:
                break
        
        return list(self.product_urls)
    
    def scrape_all_categories(self) -> List[str]:
        for category_url in config.CATEGORIES:
            self.scrape_category(category_url)
        
        return list(self.product_urls)


if __name__ == "__main__":
    scraper = CategoryScraper()
    urls = scraper.scrape_all_categories()
    print(f"\nTotal product URLs found: {len(urls)}")
    for url in urls[:10]:
        print(url)
