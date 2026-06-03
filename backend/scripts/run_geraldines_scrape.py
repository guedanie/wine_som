"""Run Geraldine's scraper — seeds wines + inventory into Supabase."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scrapers.geraldines import GeraldinesScraper


async def main():
    scraper = GeraldinesScraper()
    print("Fetching wines from shopgeraldines.com...")
    result = await scraper.run_full()
    print(f"Done!")
    print(f"  Wines:     {result['wines_fetched']}")
    print(f"  Inventory: {result['inventory_records']}")
    print(f"  Store:     {result['store']}")


asyncio.run(main())
