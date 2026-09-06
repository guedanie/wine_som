"""No scraper may write a scraper_runs.status outside the CHECK enum.

2026-09-06: kroger.py wrote status="partial". The column's CHECK constraint
allows only success|failed|running, so the terminal update raised, the
workflow's continue-on-error swallowed the APIError, and the row sat at
`running`/records=0 for two weeks. Nothing failed, so nothing complained —
while sweep_delisted skipped the retailer entirely.

The failure is invisible at write time and only shows up as an absence weeks
later, so this guards the whole directory rather than one scraper.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

VALID = {"success", "failed", "running"}
SCRAPERS = Path(__file__).parents[1] / "scrapers"

# Matches a status being assigned a literal in a scraper_runs payload or a
# `status = "..."` / `status = "a" if cond else "b"` terminal decision.
_LITERAL = re.compile(r'"status":\s*"([a-z_]+)"|status\s*=\s*"([a-z_]+)"'
                      r'(?:\s+if\s+.*?\s+else\s+"([a-z_]+)")?')


def test_no_scraper_writes_a_status_outside_the_check_enum():
    offenders = []
    for path in sorted(SCRAPERS.glob("*.py")):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for match in _LITERAL.finditer(line):
                for value in filter(None, match.groups()):
                    if value not in VALID:
                        offenders.append(f"{path.name}:{lineno} status={value!r}")
    assert not offenders, (
        "scraper_runs.status only accepts success|failed|running — these writes "
        "would raise on the terminal update and leave the run stuck at "
        "`running`:\n  " + "\n  ".join(offenders))
