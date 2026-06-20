"""
Canonical UPC normalization for cross-retailer wine deduplication.

HEB stores full 12-digit UPC-A (11-digit core + check digit).
Spec's stores the 11-digit core with a leading zero (no recomputed check).
Both normalize to the same 11-digit core. See:
docs/superpowers/specs/2026-06-20-upc-canonical-dedup-design.md
"""
from typing import Optional


def _is_valid_upca(d: str) -> bool:
    """True if d is a 12-digit string whose last digit is a valid UPC-A check digit."""
    if len(d) != 12 or not d.isdigit():
        return False
    odd = sum(int(d[i]) for i in range(0, 11, 2))
    even = sum(int(d[i]) for i in range(1, 11, 2))
    check = (10 - ((odd * 3 + even) % 10)) % 10
    return check == int(d[11])


def canonical_upc(raw: Optional[str]) -> Optional[str]:
    """
    Return the canonical 11-digit core for a retail UPC, or the input unchanged
    for synthetic IDs. Returns None for None/empty input.
    """
    if not raw:
        return None
    # Synthetic (non-barcode) IDs pass through untouched — they never collide.
    if not any(c.isdigit() for c in raw) or raw.startswith("shopify-"):
        return raw

    d = "".join(c for c in raw if c.isdigit())

    # 13-digit EAN with leading zero -> 12-digit UPC-A
    if len(d) == 13 and d.startswith("0"):
        d = d[1:]

    if len(d) == 12:
        if _is_valid_upca(d):
            return d[:11]          # HEB-style: core + check digit
        if d.startswith("0"):
            return d[1:]           # Spec's-style: 0-padded core
        return d[:11]              # invalid, no pad: best-effort drop check digit

    if len(d) == 13:
        return d[:12]              # true EAN-13: drop check digit

    return d                       # 10/11-digit oddballs: return digits unchanged
