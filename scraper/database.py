"""
Supabase database operations for fashion scraper.
Uses direct REST API calls to avoid Edge Function requirements.
"""

import os
import re
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

            # Only send columns that exist in the products table (avoid sending removed 'embedding')
            allowed_columns = {
                'id', 'source', 'product_url', 'affiliate_url', 'image_url', 'brand', 'title',
                'description', 'category', 'gender', 'metadata', 'size', 'second_hand',
                'image_embedding', 'info_embedding', 'country', 'tags', 'other', 'price', 'sale',
                'additional_images',
            }
            # Normalize: same keys across all rows, only allowed columns
            all_keys = set()
            for p in products_to_upsert:
                all_keys.update(k for k in p.keys() if k in allowed_columns)
            normalized_products = []
            for p in products_to_upsert:
                normalized = {key: p.get(key) for key in all_keys}
                normalized_products.append(normalized)

            # Use direct POST with Prefer header for upsert (matching working code)
            endpoint = f"{self.rest_client.base_url}/rest/v1/products"
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
                        headers=headers,
                        data=json.dumps(chunk),  # Use data=json.dumps() matching working code
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
            # price/sale: text, comma-separated multi-currency (e.g. "20USD,450CZK,75PLN")
            # Using source + product_url as the natural unique key
            formatted = {
                'id': product_id,  # Required: text primary key
                'source': source,
                'product_url': product_url,
                'image_url': image_url,
                'title': title,
                'brand': product.get('brand'),
                'gender': product.get('gender'),
                'price': self._format_price_text(product.get('price')) or '',  # not null in DB
                'sale': self._format_price_text(product.get('sale')) if product.get('sale') else None,
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

            # Image embedding (main product image)
            if 'image_embedding' in product and product['image_embedding'] is not None:
                formatted['image_embedding'] = product['image_embedding']

            # Info embedding (text search / AI search)
            if 'info_embedding' in product and product['info_embedding'] is not None:
                formatted['info_embedding'] = product['info_embedding']

            # Additional images (comma-separated URLs)
            if 'additional_images' in product and product['additional_images']:
                formatted['additional_images'] = product['additional_images'] if isinstance(product['additional_images'], str) else ','.join(product['additional_images'])

            # Country
            if 'country' in product and product['country']:
                formatted['country'] = product['country']

            # Tags (array)
            if 'tags' in product and product['tags']:
                formatted['tags'] = product['tags'] if isinstance(product['tags'], list) else [t.strip() for t in str(product['tags']).split(',') if t.strip()]

            # Other
            if 'other' in product and product['other']:
                formatted['other'] = product['other']

            # Optional metadata
            metadata = {}
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

    def _format_price_text(self, price_input: Any) -> Optional[str]:
        """
        Normalize price to comma-separated multi-currency text (e.g. "20USD,450CZK,75PLN").

        Args:
            price_input: Price as string (e.g. "20 USD, 450 CZK", "139,00 EUR") or list of such strings

        Returns:
            Formatted string like "20USD,450CZK,75PLN" or None if empty/invalid
        """
        if price_input is None:
            return None
        if isinstance(price_input, (list, tuple)):
            parts = []
            for item in price_input:
                p = self._format_price_text(item)
                if p:
                    # Each item might be "20USD" or "20USD,450CZK" — split and merge
                    for chunk in p.split(','):
                        if chunk.strip():
                            parts.append(chunk.strip())
            return ','.join(parts) if parts else None
        text = str(price_input).strip()
        if not text:
            return None
        # Match amount + currency: e.g. "20 USD", "450 CZK", "139,00 EUR", "75.50 PLN", "20USD"
        pattern = re.compile(r'(\d+(?:[.,]\d+)?)\s*([A-Z]{2,3})\b', re.IGNORECASE)
        pairs = []
        for m in pattern.finditer(text):
            amount = m.group(1).replace(',', '.')
            if '.' in amount and amount.endswith('.00'):
                amount = amount[:-3]  # "139.00" -> "139" optional; keep as-is for clarity
            currency = m.group(2).upper()
            pairs.append(f"{amount}{currency}")
        if pairs:
            return ','.join(pairs)
        # Fallback: treat as single value without currency, e.g. "139" -> keep raw for now
        logger.debug(f"Could not parse multi-currency from: {price_input!r}")
        return text

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
