"""Shared throttle marker for partial scrape runs.

A City Hive / Cloudflare 1015 truncates a store mid-sweep: the run commits real
wines and exits cleanly, so status=success and records_updated>0 — it looks
perfect from the outside. But the stores it never reached kept their old
last_scraped_at, and sweep_delisted would read that as "delisted" and flip
~25% of a retailer's catalog out of stock (measured 2026-08-31: 1,839 Twin
Liquors rows + 179 Frugal MacDoogal rows).

So a truncated run must SAY it was truncated, and the sweep must believe it.
scraper_runs.status has a CHECK enum of success|failed|running with no room for
'partial', so the signal rides in error_message instead — no migration needed.

Producer and consumer live far apart (a scraper at 04:00, the sweep at 05:30),
so the format is owned here rather than duplicated as a literal at each end.
"""
from typing import Iterable, Optional

_MARKER = "throttled:"


def throttle_note(store_names: Iterable[str]) -> Optional[str]:
    """Render the error_message note for a run that was rate-limited.

    Returns None when nothing was throttled — a clean run must leave
    error_message NULL, not an empty marker, or every run would read as
    partial and delisting would silently stop altogether.
    """
    names = sorted(set(store_names))
    if not names:
        return None
    return f"{_MARKER} {names}"


def was_throttled(error_message: Optional[str]) -> bool:
    """True if this run reported a rate-limit truncation, i.e. its catalog is
    incomplete and it must not be used to delist anything."""
    return _MARKER in (error_message or "")
