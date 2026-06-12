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
    sku = skus[0]  # MVP: use first SKU only; multi-pack/size products lose secondary SKUs

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


def _graphql_post(query: str, timeout: int = 20) -> Dict[str, Any]:
    """POST a GraphQL query to HEB and return the parsed JSON."""
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(GRAPHQL_URL, data=body, headers=_HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def fetch_wine_page(offset: int = 0, limit: int = 60, store_id: str = STORE_ID):
    """
    Fetch one page of wine products. Returns (server_total, [HEBProduct]).
    Non-wine rows are filtered out by _parse_record.
    """
    query = (
        "{ productSearch(shoppingContext: CURBSIDE_PICKUP, query: \"wine\", "
        f"storeId: {store_id}, limit: {limit}, offset: {offset}) {{ total records {{ {_PRODUCT_FIELDS} }} }} }}"
    )
    data = _graphql_post(query)
    ps = (data.get("data") or {}).get("productSearch") or {}
    total = ps.get("total") or 0
    products = []
    for raw in ps.get("records") or []:
        product = _parse_record(raw)
        if product:
            products.append(product)
    return total, products


class HebScraper(BaseScraper):
    """HEB scraper — pure-curl GraphQL, hardcoded to store 567 (San Antonio) for MVP."""

    def _products_to_inventory_items(self, products: List[HEBProduct]) -> List[RetailInventoryItem]:
        return [
            RetailInventoryItem(
                wine_name=p.name,
                retailer_name=RETAILER_NAME,
                zip_code=STORE_ZIP,
                upc=p.upc,
                price=p.price,
                store_name=STORE_NAME,
                store_id=STORE_ID,
                address=STORE_ADDRESS,
                city="San Antonio",
                state="TX",
                in_stock=p.in_stock,
                varietal=None,
                brand=p.brand,
            )
            for p in products
        ]

    async def search_by_zip(self, zip_code: str) -> List[RetailInventoryItem]:
        """MVP: single hardcoded store. Paginate the full wine catalog."""
        products = self._fetch_all()
        return self._products_to_inventory_items(products)

    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        _total, products = fetch_wine_page(offset=0, limit=60)
        matches = [p for p in products if wine_name.lower() in p.name.lower()]
        return self._products_to_inventory_items(matches)

    def _fetch_all(self, page_size: int = 60, max_pages: int = 60) -> List[HEBProduct]:
        """Paginate productSearch via offset until all records are fetched."""
        all_products: List[HEBProduct] = []
        offset = 0
        total = None
        for _ in range(max_pages):
            page_total, products = fetch_wine_page(offset=offset, limit=page_size)
            if total is None:
                total = page_total
            all_products.extend(products)
            offset += page_size
            if total is not None and offset >= total:
                break
        return all_products
