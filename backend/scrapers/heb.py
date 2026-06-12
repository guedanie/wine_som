"""
HEB wine scraper — pure-curl GraphQL.

HEB's storefront HTML/REST routes are behind Imperva, but the Apollo GraphQL
endpoint (POST /graphql) is reachable server-side with no auth, cookies, or
browser. We reconstructed the productSearch query by reading Apollo validation
errors (introspection is disabled). See docs and CLAUDE.md for the recipe.

Each wine record carries:
  - id, displayName, brand.name, productPageURL
  - productDescription (embeds Type/Blend/Tasting Notes/ABV as light HTML)
  - inventory.quantity (live per-store stock)
  - SKUs[].twelveDigitUPC, customerFriendlySize
  - SKUs[].contextPrices: ONLINE (in-store, canonical) + CURBSIDE
"""
import re
import json
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from scrapers.base import BaseScraper, RetailInventoryItem
from utils import infer_wine_type

GRAPHQL_URL = "https://www.heb.com/graphql"
STORE_NAME = "H-E-B"
STORE_ID = "567"
STORE_ZIP = "78208"            # Lincoln Heights, San Antonio
STORE_ADDRESS = "1520 Austin Hwy, San Antonio, TX 78218"
RETAILER_NAME = "H-E-B"

_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 Mobile/15E148",
    "Apollographql-Client-Name": "heb-com",
    "Origin": "https://www.heb.com",
    "Referer": "https://www.heb.com/",
}

_PRODUCT_FIELDS = """
  id
  displayName
  brand { name }
  productPageURL
  productDescription
  inventory { quantity }
  SKUs { twelveDigitUPC customerFriendlySize
    contextPrices { context isOnSale listPrice { amount } salePrice { amount } } }
"""


@dataclass
class HEBProduct:
    product_id: str
    name: str
    brand: Optional[str]
    upc: Optional[str]
    bottle_size: Optional[str]
    price: Optional[float]            # ONLINE context (in-store, canonical)
    curbside_price: Optional[float]   # CURBSIDE context
    in_stock: bool
    wine_type: Optional[str]
    description: Optional[str]


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def _price_for_context(context_prices: List[Dict[str, Any]], context: str) -> Optional[float]:
    """Return the sale price for a context, falling back to list price."""
    for cp in context_prices or []:
        if cp.get("context") == context:
            sale = cp.get("salePrice") or {}
            if sale.get("amount") is not None:
                return float(sale["amount"])
            listp = cp.get("listPrice") or {}
            if listp.get("amount") is not None:
                return float(listp["amount"])
    return None


def _parse_record(raw: Dict[str, Any]) -> Optional[HEBProduct]:
    """Parse a productSearch record into an HEBProduct. Returns None for non-wine / unusable rows."""
    name = raw.get("displayName") or ""
    if not name:
        return None

    skus = raw.get("SKUs") or []
    if not skus:
        return None
    sku = skus[0]

    brand = (raw.get("brand") or {}).get("name")
    wine_type = infer_wine_type(name)
    if wine_type is None:
        # Not identifiably a wine — filter out (glasses, mixers, etc.)
        return None

    context_prices = sku.get("contextPrices") or []
    price = _price_for_context(context_prices, "ONLINE")
    curbside_price = _price_for_context(context_prices, "CURBSIDE")

    quantity = (raw.get("inventory") or {}).get("quantity") or 0

    return HEBProduct(
        product_id=str(raw.get("id", "")),
        name=name,
        brand=brand,
        upc=sku.get("twelveDigitUPC"),
        bottle_size=sku.get("customerFriendlySize"),
        price=price,
        curbside_price=curbside_price,
        in_stock=quantity > 0,
        wine_type=wine_type,
        description=_strip_html(raw.get("productDescription") or "") or None,
    )
