"""
Supabase database operations for fashion scraper.
"""

import os
import logging
from typing import Dict, List, Any, Optional
from supabase import create_client, Client
from datetime import datetime

logger = logging.getLogger(__name__)

class SupabaseDB:
    def __init__(self):
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_KEY')

        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables are required")

        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        logger.info("Connected to Supabase")

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
                    # Create unique key for deduplication based on generated ID
                    product_id = formatted_product.get('id')
                    if product_id not in seen_ids:
                        seen_ids.add(product_id)
                        formatted_products.append(formatted_product)
                    else:
                        logger.debug(f"Skipping duplicate product: {product_id}")

            if not formatted_products:
                logger.warning("No valid products to upsert after formatting")
                return False

            logger.info(f"Upserting {len(formatted_products)} unique products (removed {len(products) - len(formatted_products)} duplicates)")

            # Perform upsert in batches to avoid PostgreSQL constraint issues
            batch_size = 50
            for i in range(0, len(formatted_products), batch_size):
                batch = formatted_products[i:i + batch_size]
                try:
                    result = self.client.table('products').upsert(
                        batch,
                        on_conflict='id'
                    ).execute()
                except Exception as batch_error:
                    logger.error(f"Failed to upsert batch {i//batch_size + 1}: {batch_error}")
                    # Continue with other batches
                    continue

            logger.info(f"Successfully upserted products in batches")
            return True

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

            # Generate unique ID from source and product URL
            import hashlib
            id_hash = hashlib.md5(f"{source}:{product_url}".encode()).hexdigest()
            unique_id = f"{source}_{id_hash[:16]}"

            # Build the formatted product
            formatted = {
                'id': unique_id,
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
            query = self.client.table('products').select('id', count='exact')

            if source:
                query = query.eq('source', source)

            result = query.execute()
            return result.count

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
            result = self.client.table('products').select('*').eq('source', source).order('created_at', desc=True).limit(limit).execute()
            return result.data

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
