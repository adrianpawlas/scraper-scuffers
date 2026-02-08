"""
Category inference from product title and description.
Used when URL/page context doesn't provide a category (e.g. /collections/all).
"""

from typing import Optional

# Map keywords (in title/description) to category. Order matters: more specific first.
# Matches Scuffers taxonomy: Hoodies, Knitwear, Pants, T-shirts, Polos, Shirts, Shorts,
# Outerwear, Accessories, Footwear, Crewnecks, Longsleeves, etc.
CATEGORY_KEYWORDS = [
    # Footwear (check before generic "cap" etc.)
    (['sneaker', 'sneakers', 'footwear', 'mule', 'radiant', 'suede', 'camo', 'braided', 'iconic sneaker'], 'footwear'),
    # Accessories
    (['beanie', 'beanies', 'cap', 'caps', 'belt', 'belts', 'bag', 'bags', 'duffle', 'scarf', 'scarves',
      'wallet', 'wallets', 'jewelry', 'bandana', 'bandanas', 'socks', 'underwear', 'patch', 'ff merch'], 'accessories'),
    # Clothing - specific
    (['hoodie', 'hoodies', 'zipper hoodie', 'raw hoodie'], 'hoodies'),
    (['knit', 'knitwear', 'sweater', 'pullover', 'cardigan'], 'knitwear'),
    (['crewneck', 'crewnecks'], 'crewnecks'),
    (['longsleeve', 'long sleeve', 'longsleeves', 'long sleeves'], 'longsleeves'),
    (['t-shirt', 't-shirt', 't shirt', 'tee '], 't-shirts'),
    (['polo', 'polos'], 'polos'),
    (['shirt', 'shirts', 'blouse'], 'shirts'),
    (['pants', 'trousers', 'sweatpants', 'joggers', 'chinos'], 'pants'),
    (['shorts', 'short pants'], 'shorts'),
    (['jacket', 'jackets', 'bomber', 'coat', 'puffer', 'windbreaker', 'outerwear', 'vest'], 'outerwear'),
    (['dress', 'dresses', 'skirt', 'skirts'], 'dresses'),
    (['swimwear', 'swim wear', 'bikini', 'trunks'], 'swimwear'),
    (['tank top', 'tank tops', 'tank '], 'tank tops'),
    (['basic', 'basics'], 'basics'),
]


def infer_category_from_text(title: Optional[str] = None, description: Optional[str] = None) -> Optional[str]:
    """
    Infer product category from title and/or description when URL doesn't provide it.

    Args:
        title: Product title
        description: Product description (optional)

    Returns:
        Category string (e.g. 'hoodies', 'accessories', 'footwear') or None
    """
    text = ' '.join(filter(None, [title or '', description or ''])).lower()
    if not text.strip():
        return None
    for keywords, category in CATEGORY_KEYWORDS:
        if any(kw in text for kw in keywords):
            return category
    return None
