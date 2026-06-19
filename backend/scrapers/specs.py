"""
Spec's Wines, Spirits & Finer Foods — wine scraper.

Uses the internal REST API at specsonline.com/api/search/ — no auth, no cookies,
no browser needed. Wine-only filtering via facets at the API level.

API reference: data/exploration/specs_findings.md
"""
import json
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List

from scrapers.base import BaseScraper, RetailInventoryItem
from utils import infer_wine_type

SEARCH_URL = "https://specsonline.com/api/search/"
STORE_API_URL = "https://specsonline.com/api/store/number/{}/"
RETAILER_NAME = "Spec's"
PAGE_SIZE = 96

# SA store numbers discovered via probe (see data/exploration/specs_findings.md)
# Excludes Kerrville (74) and Boerne (207) — Hill Country, not SA proper
SA_STORE_NUMBERS = [69, 72, 98, 100, 110, 113, 114, 117, 169, 171, 194, 197]

_CURL_HEADERS = [
    "-H", "Content-Type: application/json",
    "-H", "Referer: https://specsonline.com/shop/wine/",
    "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


@dataclass
class SpecsProduct:
    upc: str
    name: str
    brand: Optional[str]
    size: Optional[str]
    category_group: Optional[str]
    description: Optional[str]
    shelf_price: Optional[float]        # unitPrice / 100 (always the base price)
    sale_price: Optional[float]         # unitPricePromoDiscount / 100 (None if no promo)
    price: Optional[float]              # effective price: sale_price if available else shelf_price
    in_stock: bool


def _parse_product(raw: dict) -> Optional[SpecsProduct]:
    """Parse one product dict from the /api/search/ response. Returns None for non-wine or missing UPC."""
    details = raw.get("details") or {}
    if details.get("type", "").lower() != "wine":
        return None

    attrs = details.get("attributes") or {}
    upc = attrs.get("upc")
    if not upc:
        return None

    pricing = raw.get("pricing") or {}
    unit_cents = pricing.get("unitPrice")
    promo_cents = pricing.get("unitPricePromoDiscount")

    shelf = unit_cents / 100 if unit_cents is not None else None
    sale = promo_cents / 100 if promo_cents is not None else None
    effective = sale if sale is not None else shelf

    raw_desc = details.get("description", "")
    description = raw_desc.strip() if raw_desc and raw_desc.strip() else None

    return SpecsProduct(
        upc=upc,
        name=details.get("title", ""),
        brand=attrs.get("brand"),
        size=attrs.get("size"),
        category_group=attrs.get("categoryGroup"),
        description=description,
        shelf_price=shelf,
        sale_price=sale,
        price=effective,
        in_stock=raw.get("stock", {}).get("inStock", False),
    )


def _fetch_wine_page(store_number: int, page: int, page_size: int = PAGE_SIZE) -> dict:
    """POST to /api/search/ for one page of wines at a given store. Returns raw API response dict."""
    body = json.dumps({
        "userQuery": "",
        "orderBy": "popularity",
        "storeNumber": store_number,
        "page": page,
        "pageSize": page_size,
        "facets": {"category.keyword": "[\"Wine\"]"},
    })
    cmd = (
        ["curl", "-s", "-X", "POST", "--max-time", "30"]
        + _CURL_HEADERS
        + ["-d", body, SEARCH_URL]
    )
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)
