import requests
from bs4 import BeautifulSoup
import time
import json
import re
import logging
from typing import Dict, Any, List, Optional
from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProductScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
    
    def get_page(self, url: str):
        for attempt in range(config.MAX_RETRIES):
            try:
                response = self.session.get(url, timeout=config.TIMEOUT)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "lxml")
                
                product_json = self.extract_shopify_product_json(soup)
                
                return soup, product_json
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < config.MAX_RETRIES - 1:
                    time.sleep(config.DELAY_BETWEEN_REQUESTS * (attempt + 1))
                else:
                    raise
        return None, None
    
    def extract_shopify_product_json(self, soup: BeautifulSoup) -> Optional[Dict]:
        scripts = soup.find_all("script")
        for script in scripts:
            if script.string and "sizeChartsRelentless.product" in script.string:
                try:
                    match = re.search(r'sizeChartsRelentless\.product\s*=\s*(\{.+?\});', script.string, re.DOTALL)
                    if match:
                        return json.loads(match.group(1))
                except Exception as e:
                    logger.warning(f"Failed to parse Shopify product JSON: {e}")
        return None
    
    def extract_gender_from_type(self, product_type: str) -> str:
        if not product_type:
            return ""
        
        type_lower = product_type.lower()
        
        woman_keywords = ["woman", "donna", "dam", "women", "lady", "female", "she"]
        man_keywords = ["man", "herr", "men", "uomo", "male", "he"]
        
        for kw in woman_keywords:
            if kw in type_lower:
                return "woman"
        
        for kw in man_keywords:
            if kw in type_lower:
                return "man"
        
        return ""
    
    def extract_category_from_type(self, product_type: str) -> str:
        if not product_type:
            return ""
        
        type_str = product_type
        
        parts = type_str.split()
        category_parts = []
        
        for part in parts:
            if part.lower() in ["man", "woman", "standard"]:
                continue
            category_parts.append(part)
        
        return " ".join(category_parts) if category_parts else type_str
    
    def extract_title(self, soup: BeautifulSoup, product_json: Dict = None) -> str:
        if product_json and product_json.get("title"):
            return product_json["title"]
        
        h1 = soup.select_one("h1.product__title")
        if h1:
            return h1.get_text(strip=True)
        
        title = soup.select_one("h1")
        if title:
            return title.get_text(strip=True)
        
        return ""
    
    def extract_description(self, soup: BeautifulSoup, product_json: Dict = None) -> str:
        if product_json and product_json.get("description"):
            desc = product_json["description"]
            desc = re.sub(r'<[^>]+>', '', desc)
            return desc.strip()
        
        desc = soup.select_one("div.product__description")
        if desc:
            return desc.get_text(strip=True)
        
        return ""
    
    def extract_price_from_html(self, soup: BeautifulSoup) -> str:
        CZK_TO_EUR = 0.042
        
        price_elem = soup.select_one('.price, .product__price, [class*="price"]')
        if price_elem:
            text = price_elem.get_text(strip=True)
            
            match = re.search(r'([\d\s.,]+)\s*CZK', text)
            if match:
                value = match.group(1).replace(' ', '').replace('.', '').replace(',', '.')
                try:
                    czk = float(value)
                    eur = czk * CZK_TO_EUR
                    return f"{eur:.2f}EUR"
                except:
                    pass
            
            match = re.search(r'([\d\s,]+)\s*EUR', text)
            if match:
                value = match.group(1).replace(',', '.').replace(' ', '')
                try:
                    return f"{float(value):.2f}EUR"
                except:
                    pass
        
        return ""
    
    def extract_price_from_json(self, product_json: Dict = None) -> tuple:
        price_str = ""
        sale_price_str = ""
        
        if product_json:
            base_price = product_json.get("price")
            if base_price:
                price_value = float(base_price) / 100
                price_str = f"{price_value:.2f}EUR"
        
        return price_str, sale_price_str
    
    def extract_images(self, soup: BeautifulSoup, product_json: Dict = None) -> tuple:
        main_image = ""
        additional_images = []
        
        if product_json:
            images = product_json.get("images", [])
            if images:
                main_image = images[0] if images else ""
                if main_image and str(main_image).startswith("//"):
                    main_image = "https:" + str(main_image)
                additional_images = [str(img) if not str(img).startswith("//") else "https:" + str(img) for img in images[1:] if img]
        
        if not main_image:
            main_img = soup.select_one("img.product__media img, img.product-featured-image")
            if main_img:
                main_image = main_img.get("src", "")
        
        if main_image and str(main_image).startswith("//"):
            main_image = "https:" + str(main_image)
        
        if not additional_images:
            gallery_images = soup.select("img.product__media-thumbnail, img.product-thumbnail")
            for img in gallery_images:
                src = img.get("src", "")
                if src and str(src).startswith("//"):
                    src = "https:" + str(src)
                if src and src != main_image and src not in additional_images:
                    additional_images.append(src)
        
        return main_image, additional_images
    
    def extract_gender(self, soup: BeautifulSoup, url: str, product_json: Dict = None) -> str:
        if product_json and product_json.get("type"):
            gender = self.extract_gender_from_type(product_json["type"])
            if gender:
                return gender
        
        url_lower = url.lower()
        
        if "/woman" in url_lower or "/women" in url_lower:
            return "woman"
        elif "/man" in url_lower or "/men" in url_lower:
            return "man"
        
        return ""
    
    def extract_category(self, soup: BeautifulSoup, url: str, product_json: Dict = None) -> str:
        if product_json and product_json.get("type"):
            category = self.extract_category_from_type(product_json["type"])
            if category:
                return category
        
        categories = []
        
        breadcrumbs = soup.select("nav.breadcrumb a, ol.breadcrumb a, div.breadcrumb a, ul.breadcrumb a")
        for link in breadcrumbs:
            text = link.get_text(strip=True)
            if text and text.lower() not in ["home", "inicio", "collections", "all"]:
                if text.lower() not in [c.lower() for c in categories]:
                    categories.append(text)
        
        return " , ".join(categories) if categories else ""
    
    def extract_sizes(self, soup: BeautifulSoup, product_json: Dict = None) -> List[str]:
        sizes = []
        
        if product_json:
            variants = product_json.get("variants", [])
            for v in variants:
                title = v.get("title", "")
                if title and title != "Default Title":
                    sizes.append(title)
        
        return list(set(sizes))
    
    def extract_colors(self, soup: BeautifulSoup) -> List[str]:
        return []
    
    def extract_metadata(self, soup: BeautifulSoup, product_json: Dict = None, title: str = "", 
                         description: str = "", price: str = "", sizes: List[str] = [], 
                         colors: List[str] = [], category: str = "", gender: str = "") -> str:
        
        metadata = {
            "title": title,
            "description": description,
            "price": price,
            "category": category,
            "gender": gender,
            "sizes": sizes,
            "colors": colors,
        }
        
        if product_json:
            metadata["product_type"] = product_json.get("type", "")
            metadata["vendor"] = product_json.get("vendor", "")
            metadata["tags"] = product_json.get("tags", [])
            
            variants = product_json.get("variants", [])
            if variants:
                variant_info = []
                for v in variants:
                    var_price = v.get("price")
                    if var_price:
                        var_price = float(var_price) / 100
                    var_data = {
                        "title": v.get("title"),
                        "price_eur": f"{var_price:.2f}EUR" if var_price else None,
                        "sku": v.get("sku"),
                        "available": v.get("available")
                    }
                    variant_info.append(var_data)
                metadata["variants"] = variant_info
        
        return json.dumps(metadata, ensure_ascii=False)
    
    def extract_product_id(self, url: str, product_json: Dict = None) -> str:
        if product_json and product_json.get("handle"):
            return product_json["handle"]
        
        match = re.search(r'/products/([^/?#]+)', url)
        if match:
            return match.group(1)
        
        return url.split("/")[-1].split("?")[0]
    
    def scrape_product(self, url: str) -> Dict[str, Any]:
        logger.info(f"Scraping product: {url}")
        
        soup, product_json = self.get_page(url)
        if not soup:
            return None
        
        product_id = self.extract_product_id(url, product_json)
        title = self.extract_title(soup, product_json)
        description = self.extract_description(soup, product_json)
        
        price = self.extract_price_from_html(soup)
        sale_price = ""
        if not price:
            price, sale_price = self.extract_price_from_json(product_json)
        
        main_image, additional_images = self.extract_images(soup, product_json)
        
        gender = self.extract_gender(soup, url, product_json)
        category = self.extract_category(soup, url, product_json)
        
        sizes = self.extract_sizes(soup, product_json)
        colors = self.extract_colors(soup)
        
        metadata = self.extract_metadata(
            soup, product_json, title, description, price, sizes, colors, category, gender
        )
        
        additional_images_str = " , ".join(additional_images) if additional_images else ""
        
        product_data = {
            "id": product_id,
            "source": config.SOURCE,
            "product_url": url,
            "affiliate_url": None,
            "image_url": main_image,
            "brand": config.BRAND,
            "title": title,
            "description": description,
            "category": category,
            "gender": gender,
            "second_hand": config.SECOND_HAND,
            "price": price,
            "sale": sale_price if sale_price else price,
            "metadata": metadata,
            "size": ", ".join(sizes) if sizes else None,
            "additional_images": additional_images_str,
            "created_at": None,
        }
        
        return product_data


if __name__ == "__main__":
    scraper = ProductScraper()
    test_urls = [
        "https://scuffers.com/products/lizzie-burgundy-hoodie",
    ]
    
    for url in test_urls:
        try:
            data = scraper.scrape_product(url)
            print(f"\n=== {url} ===")
            print(f"Title: {data.get('title')}")
            print(f"Price: {data.get('price')}")
            print(f"Gender: {data.get('gender')}")
            print(f"Category: {data.get('category')}")
        except Exception as e:
            print(f"Error scraping {url}: {e}")
