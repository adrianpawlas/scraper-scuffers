"""
Supabase database operations for fashion scraper.
Uses direct REST API calls to avoid Edge Function requirements.
"""

import os
import logging
import hashlib
import json
from typing import Dict, List, Any, Optional
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

class SupabaseREST:
    """
    Minimal Supabase PostgREST helper for upserting into 'products' table.
    Uses direct REST API calls instead of the official client to avoid Edge Function requirements.
    """
    def __init__(self, url: str = None, key: str = None):
        self.base_url = (url or os.getenv('SUPABASE_URL', '')).rstrip("/")
        self.key = key or os.getenv('SUPABASE_KEY', '')

        if not self.base_url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables are required")

        self.session = requests.Session()
        self.session.headers.update({
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        })
        logger.info("Connected to Supabase via REST API")

class SupabaseDB:
    def __init__(self):
        self.rest_client = SupabaseREST()

    def upsert_products(self, products: List[Dict[str, Any]]) -> bool:
        """
        Upsert products into the database.

        Args:
            products: List of product dictionaries

        Returns:
            True if successful, False otherwise
        """
        if not products:
            logger.warning("No products to upsert")
            return True

        try:
            # Convert products to the expected format
            formatted_products = []
            seen_ids = set()  # Track unique IDs

            for product in products:
                formatted_product = self._format_product_for_db(product)
                if formatted_product:
                    # Create unique key for deduplication based on source and product_url
                    dedup_key = f"{formatted_product.get('source')}:{formatted_product.get('product_url')}"
                    if dedup_key not in seen_ids:
                        seen_ids.add(dedup_key)
                        formatted_products.append(formatted_product)
                    else:
                        logger.debug(f"Skipping duplicate product: {dedup_key}")

            if not formatted_products:
                logger.warning("No valid products to upsert after formatting")
                return False

            logger.info(f"Upserting {len(formatted_products)} unique products (removed {len(products) - len(formatted_products)} duplicates)")

            # Deduplicate by 'id' within this batch to avoid conflicts
            seen: Dict[str, Dict] = {}
            for p in formatted_products:
                key = p.get('id')
                if key:
                    seen[key] = p

            products_to_upsert = list(seen.values())

            # Normalize all products to have the same keys (Supabase requirement)
            all_keys = set()
            for p in products_to_upsert:
                all_keys.update(p.keys())

            # Ensure every product has all keys (fill missing with None)
            normalized_products = []
            for p in products_to_upsert:
                normalized = {key: p.get(key) for key in all_keys}
                normalized_products.append(normalized)

            # Use on_conflict query parameter for upsert
            endpoint = f"{self.rest_client.base_url}/rest/v1/products"
            params = {"on_conflict": "source,product_url"}
            headers = {
                "Prefer": "resolution=merge-duplicates,return=minimal",
            }

            # Chunk inserts to keep requests reasonable (metadata can be large)
            chunk_size = 100
            success_count = 0
            for i in range(0, len(normalized_products), chunk_size):
                chunk = normalized_products[i:i + chunk_size]
                try:
                    resp = self.rest_client.session.post(
                        endpoint,
                        params=params,
                        headers=headers,
                        json=chunk,  # Use json parameter instead of data=json.dumps()
                        timeout=60
                    )
                    if resp.status_code not in (200, 201, 204):
                        logger.error(f"Failed to upsert batch {i//chunk_size + 1}: {resp.status_code} {resp.text}")
                        continue
                    success_count += len(chunk)
                except Exception as batch_error:
                    logger.error(f"Failed to upsert batch {i//chunk_size + 1}: {batch_error}")
                    continue

            logger.info(f"Successfully upserted {success_count} products in batches")
            return success_count > 0

        except Exception as e:
            logger.error(f"Failed to upsert products: {e}")
            return False

    def _format_product_for_db(self, product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Format a product dictionary for database insertion.

        Args:
            product: Raw product data

        Returns:
            Formatted product data or None if invalid
        """
        try:
            # Required fields
            source = product.get('source')
            product_url = product.get('product_url')
            image_url = product.get('image_url')
            title = product.get('title')

            if not source or not product_url or not image_url or not title:
                logger.warning(f"Missing required fields (source, product_url, image_url, title): {product}")
                return None

            # Generate deterministic ID from source and product_url
            # This ensures the same product always gets the same ID
            id_string = f"{source}:{product_url}"
            product_id = hashlib.sha256(id_string.encode('utf-8')).hexdigest()

            # Build the formatted product
            # Using source + product_url as the natural unique key
            formatted = {
                'id': product_id,  # Required: text primary key
                'source': source,
                'product_url': product_url,
                'image_url': image_url,
                'title': title,
                'brand': product.get('brand'),
                'gender': product.get('gender'),
                'price': self._parse_price(product.get('price')),
                'currency': product.get('currency', 'EUR'),
                'size': product.get('size'),
                'second_hand': product.get('second_hand', False)
            }

            # Optional fields
            if 'affiliate_url' in product and product['affiliate_url']:
                formatted['affiliate_url'] = product['affiliate_url']
            if 'description' in product and product['description']:
                formatted['description'] = product['description']
            if 'category' in product and product['category']:
                formatted['category'] = product['category']

            # Optional embedding
            if 'embedding' in product and product['embedding'] is not None:
                formatted['embedding'] = product['embedding']

            # Optional metadata
            metadata = {}
            if 'original_currency' in product:
                metadata['original_currency'] = product['original_currency']
            if 'merchant_name' in product:
                metadata['merchant_name'] = product['merchant_name']
            if 'country' in product:
                metadata['country'] = product['country']
            if metadata:
                import json
                formatted['metadata'] = json.dumps(metadata)

            return formatted

        except Exception as e:
            logger.error(f"Failed to format product: {e}")
            return None

    def _parse_price(self, price_str: Optional[str]) -> Optional[float]:
        """
        Parse price string to float.

        Args:
            price_str: Price as string (e.g., "139,00 EUR", "139.00")

        Returns:
            Price as float or None if parsing failed
        """
        if not price_str:
            return None

        try:
            # Remove currency symbols and extra text
            price_str = str(price_str).strip()

            # Handle European format (139,00) and convert to (139.00)
            if ',' in price_str and '.' not in price_str:
                # European format: 139,00
                price_str = price_str.replace(',', '.')
            elif ',' in price_str and '.' in price_str:
                # Mixed format: remove commas if they're thousands separators
                price_str = price_str.replace(',', '')

            # Extract numeric part
            import re
            match = re.search(r'[\d.]+', price_str)
            if match:
                return float(match.group())
            else:
                logger.warning(f"Could not parse price: {price_str}")
                return None

        except Exception as e:
            logger.error(f"Failed to parse price '{price_str}': {e}")
            return None

    def get_product_count(self, source: Optional[str] = None) -> int:
        """
        Get count of products in database.

        Args:
            source: Optional source filter

        Returns:
            Number of products
        """
        try:
            url = f"{self.rest_client.base_url}/rest/v1/products"
            params = {"select": "id"}
            if source:
                params["source"] = f"eq.{source}"
            
            resp = self.rest_client.session.get(url, params=params, timeout=60)
            resp.raise_for_status()
            return len(resp.json())

        except Exception as e:
            logger.error(f"Failed to get product count: {e}")
            return 0

    def get_recent_products(self, source: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recently created products for a source.

        Args:
            source: Source name
            limit: Maximum number of products to return

        Returns:
            List of recent products
        """
        try:
            url = f"{self.rest_client.base_url}/rest/v1/products"
            params = {
                "source": f"eq.{source}",
                "order": "created_at.desc",
                "limit": str(limit)
            }
            resp = self.rest_client.session.get(url, params=params, timeout=60)
            resp.raise_for_status()
            return resp.json()

        except Exception as e:
            logger.error(f"Failed to get recent products: {e}")
            return []


# Global instance
_db_instance = None

def get_db() -> SupabaseDB:
    """Get global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = SupabaseDB()
    return _db_instance


def upsert_products(products: List[Dict[str, Any]]) -> bool:
    """Convenience function to upsert products."""
    return get_db().upsert_products(products)
