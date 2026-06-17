"""
One-time script: populate latitude/longitude for stores that have a zip_code but no coords.

Usage:
    cd backend
    python3 scripts/backfill_store_coords.py
"""
import sys
import os

# Add parent directory (backend/) to path so we can import db, utils, etc.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_service_client
from utils.geo import zip_to_centroid


def main():
    db = get_service_client()
    stores = db.table("stores").select("id,name,zip_code,latitude").execute()
    updated = 0
    for s in stores.data:
        if s.get("latitude") is not None:
            print(f"  skip {s['name']} (already has coords)")
            continue
        if not s.get("zip_code"):
            print(f"  skip {s['name']} (no zip)")
            continue
        coords = zip_to_centroid(s["zip_code"])
        if coords is None:
            print(f"  warn: unknown zip {s['zip_code']} for {s['name']}")
            continue
        db.table("stores").update({
            "latitude": coords[0],
            "longitude": coords[1],
        }).eq("id", s["id"]).execute()
        print(f"  updated {s['name']}: {coords}")
        updated += 1
    print(f"\nDone — {updated} stores updated")


if __name__ == "__main__":
    main()
