"""
GrapeMinds API client.

Key constraints discovered during API exploration:
  - Must use curl via subprocess — Python urllib/requests are blocked by Cloudflare TLS fingerprinting
  - Auth: Authorization: Bearer <key> only (X-API-Key header does NOT work)
  - First request for a wine triggers async AI content generation and returns nulls
  - Second request (~60s later) returns fully populated data (two-step warm-up)
  - Monthly budget: 250 calls — always check DB cache before calling
"""
import json
import subprocess
from dataclasses import dataclass, field
from typing import Optional, List

BASE_URL = "https://api.grapeminds.eu/public/v1"


@dataclass
class GrapeMindsWine:
    grapeminds_id: str
    display_name: str
    color: Optional[str] = None
    producer_name: Optional[str] = None
    region_name: Optional[str] = None
    grapes: List[str] = field(default_factory=list)
    description: Optional[str] = None
    description_long: Optional[str] = None
    tasting_notes: Optional[str] = None
    tasting_notes_long: Optional[str] = None
    pairing: Optional[str] = None
    pairing_long: Optional[str] = None
    # 1-10 scale: sweetness, acidity, tannins, alcohol, body, finish
    structure_profile: dict = field(default_factory=dict)
    is_fully_enriched: bool = False


@dataclass
class DrinkingPeriod:
    from_year: Optional[int] = None
    to_year: Optional[int] = None
    statement: Optional[str] = None
    young: Optional[str] = None
    ripe: Optional[str] = None
    storage: Optional[str] = None


class GrapeMindsClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def _call(self, path: str) -> dict:
        """Make a GET request via curl — bypasses Cloudflare TLS fingerprint block."""
        result = subprocess.run(
            [
                "curl", "-s",
                "-H", f"Authorization: Bearer {self.api_key}",
                "-H", "Accept-Language: en",
                f"{BASE_URL}{path}",
            ],
            capture_output=True, text=True, timeout=20,
        )
        if not result.stdout.strip():
            return {}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {}

    def _parse_text_field(self, field_val) -> tuple:
        """Parse a GrapeMinds text field that has {text, text_long} shape. Returns (short, long)."""
        if not field_val or not isinstance(field_val, dict):
            return None, None
        return field_val.get("text"), field_val.get("text_long")

    def _parse_detail(self, payload: dict) -> Optional[GrapeMindsWine]:
        d = payload.get("data")
        if not d:
            return None

        fp = d.get("flavor_profile") or {}
        desc_short, desc_long = self._parse_text_field(d.get("description"))
        notes_short, notes_long = self._parse_text_field(d.get("tasting_notes"))
        pairing_short, pairing_long = self._parse_text_field(d.get("pairing"))
        grapes = [g["name"] for g in (d.get("grapes") or []) if g.get("name")]
        is_enriched = bool(fp or desc_short or notes_short)

        return GrapeMindsWine(
            grapeminds_id=str(d.get("id", "")),
            display_name=d.get("display_name", ""),
            color=d.get("color"),
            producer_name=(d.get("producer") or {}).get("name"),
            region_name=(d.get("region") or {}).get("name"),
            grapes=grapes,
            description=desc_short,
            description_long=desc_long,
            tasting_notes=notes_short,
            tasting_notes_long=notes_long,
            pairing=pairing_short,
            pairing_long=pairing_long,
            structure_profile=fp if isinstance(fp, dict) else {},
            is_fully_enriched=is_enriched,
        )

    def _parse_drinking_period(self, payload: dict) -> Optional[DrinkingPeriod]:
        """Returns None when the API is still generating content (generating: true)."""
        if payload.get("generating") or payload.get("error"):
            return None
        return DrinkingPeriod(
            from_year=payload.get("from"),
            to_year=payload.get("to"),
            statement=payload.get("statement"),
            young=payload.get("young"),
            ripe=payload.get("ripe"),
            storage=payload.get("storage"),
        )

    def search(self, wine_name: str, limit: int = 5) -> List[dict]:
        """Search wines by name. Returns list of summary dicts with id + display_name."""
        q = wine_name.replace(" ", "+")
        payload = self._call(f"/wines/search?q={q}&limit={limit}")
        return payload.get("data", [])

    def get_wine(self, grapeminds_id: int) -> Optional[GrapeMindsWine]:
        """Fetch full wine detail. Returns None if API call fails."""
        payload = self._call(f"/wines/{grapeminds_id}")
        return self._parse_detail(payload)

    def get_drinking_period(self, grapeminds_id: int) -> Optional[DrinkingPeriod]:
        """
        Fetch drinking window. Returns None if still generating (first call).
        Re-fetch after ~60s to get populated data.
        """
        payload = self._call(f"/drinking-periods/{grapeminds_id}")
        return self._parse_drinking_period(payload)
