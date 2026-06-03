"""
Seed wines and retail_inventory from the HEB Fair Oaks CSV.

CSV column mapping (confirmed from actual headers):
  id_upc              -> wines.upc, retail_inventory.upc
  cust_frndly1_des    -> wines.name (part 1)
  cust_frndly2_des    -> wines.name (part 2, appended if non-empty)
  dsc_brand           -> wines.brand
  dsc_coo             -> wines.country
  dsc_sub_comm        -> wines.varietal (also used to infer wine_type)
  id_str              -> retail_inventory.store_id
  cust_frndly_nm      -> retail_inventory.store_name
  add_str             -> retail_inventory.address
  cd_zip              -> retail_inventory.zip_code
  sz_item             -> wines.bottle_size
  aip                 -> retail_inventory.price
  max_sales_date      -> retail_inventory.last_scraped_at

Run from project root:
  python3 backend/scripts/seed_from_csv.py
"""

import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parents[1]))
from db import get_service_client

RED_VARIETALS = {
    "cabernet sauvignon", "merlot", "pinot noir", "syrah", "shiraz",
    "malbec", "zinfandel", "sangiovese", "tempranillo", "grenache", "red blend",
    "cabernet", "petit verdot", "malbec", "petite sirah",
}
WHITE_VARIETALS = {
    "chardonnay", "sauvignon blanc", "pinot grigio", "pinot gris",
    "riesling", "albarino", "viognier", "white blend", "moscato",
    "gewurztraminer", "chenin blanc",
}
SPARKLING_TERMS = {"prosecco", "champagne", "cava", "sparkling", "cremant", "crémant"}
ROSE_TERMS = {"rosé", "rose", "rosado"}


def _infer_wine_type(sub_comm: str) -> Optional[str]:
    s = sub_comm.lower()
    if any(t in s for t in SPARKLING_TERMS):
        return "sparkling"
    if any(t in s for t in ROSE_TERMS):
        return "rosé"
    if any(t in s for t in RED_VARIETALS):
        return "red"
    if any(t in s for t in WHITE_VARIETALS):
        return "white"
    return None


@dataclass
class CsvRow:
    upc: Optional[str]
    wine_name: str
    brand: Optional[str]
    country: Optional[str]
    varietal: Optional[str]
    wine_type: Optional[str]
    store_id: Optional[str]
    store_name: Optional[str]
    address: Optional[str]
    zip_code: Optional[str]
    bottle_size: Optional[str]
    price: Optional[float]
    last_scraped_at: Optional[str]


def parse_row(raw: dict) -> CsvRow:
    name1 = raw.get("cust_frndly1_des", "").strip()
    name2 = raw.get("cust_frndly2_des", "").strip()
    wine_name = f"{name1} {name2}".strip() if name2 else name1
    sub_comm = raw.get("dsc_sub_comm", "").strip()
    price_str = raw.get("aip", "").strip()
    return CsvRow(
        upc=raw.get("id_upc", "").strip() or None,
        wine_name=wine_name,
        brand=raw.get("dsc_brand", "").strip() or None,
        country=raw.get("dsc_coo", "").strip() or None,
        varietal=sub_comm or None,
        wine_type=_infer_wine_type(sub_comm),
        store_id=raw.get("id_str", "").strip() or None,
        store_name=raw.get("cust_frndly_nm", "").strip() or None,
        address=raw.get("add_str", "").strip() or None,
        zip_code=raw.get("cd_zip", "").strip() or None,
        bottle_size=raw.get("sz_item", "").strip() or None,
        price=float(price_str) if price_str else None,
        last_scraped_at=raw.get("max_sales_date", "").strip() or None,
    )


def seed(csv_path: Path):
    client = get_service_client()

    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for raw in csv.DictReader(f):
            rows.append(parse_row(raw))

    print(f"Parsed {len(rows)} rows from CSV")

    # Upsert wines — deduplicate by UPC, skip rows without a name
    seen_upcs = set()
    wine_records = []
    for r in rows:
        if not r.wine_name:
            continue
        if r.upc and r.upc in seen_upcs:
            continue
        if r.upc:
            seen_upcs.add(r.upc)
        record = {k: v for k, v in {
            "upc": r.upc,
            "name": r.wine_name,
            "brand": r.brand,
            "country": r.country,
            "varietal": r.varietal,
            "wine_type": r.wine_type,
            "bottle_size": r.bottle_size,
            "avg_price": r.price,
        }.items() if v is not None}
        wine_records.append(record)

    # Upsert in batches of 500 to stay within Supabase request limits
    batch_size = 500
    for i in range(0, len(wine_records), batch_size):
        batch = wine_records[i:i + batch_size]
        client.table("wines").upsert(batch, on_conflict="upc").execute()
    print(f"Upserted {len(wine_records)} wines")

    # Build UPC -> ID map for inventory foreign keys
    result = client.table("wines").select("id,upc").execute()
    upc_to_id = {w["upc"]: w["id"] for w in result.data if w["upc"]}

    # Upsert inventory records (all rows, including duplicates by UPC across stores)
    inv_records = []
    for r in rows:
        wine_id = upc_to_id.get(r.upc) if r.upc else None
        record = {k: v for k, v in {
            "wine_id": wine_id,
            "upc": r.upc,
            "retailer_name": "HEB",
            "store_id": r.store_id,
            "store_name": r.store_name,
            "address": r.address,
            "zip_code": r.zip_code,
            "price": r.price,
            "in_stock": True,
            "last_scraped_at": r.last_scraped_at,
        }.items() if v is not None}
        inv_records.append(record)

    for i in range(0, len(inv_records), batch_size):
        batch = inv_records[i:i + batch_size]
        client.table("retail_inventory").upsert(
            batch, on_conflict="upc,store_id"
        ).execute()
    print(f"Upserted {len(inv_records)} inventory records")

    # Summary
    w_count = client.table("wines").select("id", count="exact").execute()
    i_count = client.table("retail_inventory").select("id", count="exact").execute()
    z_count = client.table("retail_inventory").select("zip_code").execute()
    stores = {r["zip_code"] for r in z_count.data if r["zip_code"]}
    print(f"\nDB totals: {w_count.count} wines | {i_count.count} inventory records | {len(stores)} zip codes")


if __name__ == "__main__":
    csv_path = Path(__file__).parents[2] / "data" / "seed" / "Fair_Oaks_Stores_Analysis.csv"
    if not csv_path.exists():
        sys.exit(f"CSV not found at {csv_path}")
    seed(csv_path)
