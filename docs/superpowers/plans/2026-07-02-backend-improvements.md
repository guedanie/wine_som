# Backend Improvements — Code Review 2026-07-02

Findings from a full backend survey. Grouped by theme with priority notes.
Items marked **[NEXT]** are the agreed first batch to implement.

---

## Performance

| ID | File | Issue | Fix |
|----|------|--------|-----|
| **P1** [NEXT] | `utils/geo.py:51` | `find_nearby_store_ids` fetches every store row with no filter, then filters in Python. Called on every `/api/recommend`. | Module-level TTL cache (60s) on the store list. |
| **P2** [NEXT] | `db.py` | `get_supabase_client()` / `get_service_client()` call `create_client()` on every invocation — once per request. | Module-level singletons; client is stateless and thread-safe. |
| **P3** [NEXT] | All routers | Every `db.table(...).execute()` is a sync HTTP call on the event loop thread — blocks concurrent requests. | Wrap in `asyncio.to_thread()` or switch to async PostgREST client. Highest-throughput fix. |
| **P4** [NEXT] | `intent.py:40`, `claude_client.py:236`, `somm.py` | `anthropic.Anthropic(api_key=...)` re-instantiated inside each function call. | Module-level constants in each file. |
| **P5** | `enrichment.py:51` | `enrich_pending` fetches first 200 wines then Python-side diffs vs enriched IDs. Returns "nothing to enrich" if all 200 are already done even when unenriched wines exist beyond offset 200. | DB-side filter: `WHERE vivino_enriched_at IS NULL` (or grapeminds equivalent). |
| **P6** | `vivino.py:60` | Spawns a new OS process (`subprocess curl`) per wine page fetch. Vivino has no Cloudflare constraint. | Replace with `requests` or `httpx`. |
| **P7** | `claude_client.py:327` | `_try_extract_picks(post_buf)` rescans full buffer from byte 0 on every fragment. | Add a "start marker already found at offset N" short-circuit. |

---

## Correctness / Bugs

| ID | File | Issue | Fix |
|----|------|--------|-----|
| **B1** [NEXT] | `wines.py:43` | `.single()` raises PGRST116 (not None) when wine missing → raw 500. `data or {}` is never reached. | Use `.maybe_single()`, raise `HTTPException(404)` when `data is None`. |
| **B2** [NEXT] | `claude_client.py:289` | `_JSON_ESCAPES` missing `\uXXXX` handling. Wine names with accents/smart-quotes (é, ñ, ') stream as literal `u0e9` etc. | Add `\u` case: read 4 hex digits, emit `chr(int(hex, 16))`. |
| **B3** | `geraldines.py:216` | `varietal=p.product_type` stores `"Red Wine"` / `"White Wine"` as a grape varietal. Degrades scorer and Claude context. | Set `varietal=None`; let extraction pipeline fill it. |
| **B4** | `pipeline.py:131` | `persist_candidates` does DELETE then INSERT — non-atomic. INSERT failure permanently deletes candidates. | Upsert on `(wine_id, grapeminds_id)`. |
| **B5** | `pipeline.py:108` | `_persist()` skips `None` values — can't clear a GrapeMinds field that was previously set. Stale data survives refetches. | Separate "fields to clear" from "fields to set"; issue explicit `null` for cleared fields. |
| **B6** | `claude_client.py:366` | Characters after closing `"` in a fragment are dropped from `post_buf` (remaining chars in fragment after narrative end). | After setting `narrative_done`, append rest of fragment to `post_buf` before breaking. |
| **B7** | `grapeminds.py:239` | `int(result.grapeminds_id)` — implicit invariant that `grapeminds_id` is non-None when `needs_refetch` is True. | Add explicit guard: `if not result.grapeminds_id: return result`. |
| **B8** | `grapeminds.py:64` | Curl timeout, 503, and genuine empty response all return `{}` — caller permanently marks wine as `source="error"`. | Check curl exit code and response body; distinguish transient vs. not-found. |

---

## Error Handling

| ID | File | Issue | Fix |
|----|------|--------|-----|
| **E1** [NEXT] | `feedback.py:11` | Zero error handling on the thumbs vote endpoint — any Supabase error returns raw 500. Customer-facing. | `try/except`, log, return clean `{"ok": False, "error": "..."}`. |
| **E2** | `recommend.py:257` | `except Exception: pass` swallows session persistence failures silently — no log trace. | Replace with `logger.warning(...)`. |
| **E3** | `grapeminds.py:64` | See B8. Transient GrapeMinds outage permanently marks wines as errored. | Retry logic (1–2 retries with backoff) before marking error. |
| **E4** | `somm.py:70` | `str(e)` on Anthropic exception can expose quota/rate-limit details to browser. | Sanitize: return generic `"Something went wrong"` message to client; log full error server-side. |
| **E5** | `recommend.py` | Mid-stream Supabase error inside `event_gen()` after `200 OK` is committed → client receives truncated SSE with no error event. | Yield `data: {"type":"error","message":"..."}` in the generator's except branch. |
| **E6** | `pipeline.py:271` | Error log uses wine name (not unique); uses `print()` not `logger.exception()`. Stack trace lost. | `logger.exception("wine_id=%s name=%r", wine_id, name)`. |

---

## Test Gaps

| ID | What's missing | Priority |
|----|---------------|----------|
| **T1** [NEXT] | SSE streaming state machine in `claude_client.py` — `_gen()`, `_JSON_ESCAPES`, narrative markers, `_try_extract_picks()`, escape handling, fallback path. Highest-complexity code, zero tests. | Critical |
| **T2** | `/api/wines/{wine_id}` — zero tests including the 500-instead-of-404 bug (B1). | High |
| **T3** | `/api/enrich/` endpoints — zero tests including pending-set logic (P5). | High |
| **T4** | `_detect_retailer()` and retailer pool filtering in `recommend.py:194` — 6 alias variants, none exercised. | Medium |
| **T5** | `FLAVOR_VOCAB` parity between `intent.py` and `flavor_profiles.py` — drift goes undetected. | Medium |
| **T6** | Region dedup (lowest-price-wins) and `_PER_RETAILER_LIMIT` cap in `region.py:107`. | Medium |
| **T7** | `enrich_batch` refetch pass in `pipeline.py:274` (single-wine refetch covered; batch flow is not). | Low |
| **T8** | `infer_wine_type()` edge cases — sparkling+red conflict, rosado/rosé/rose variants, orange wine. | Low |
| **T9** | `GeraldinesScraper._upsert_wine_details()` name-based wine ID lookup. | Low |

---

## Maintainability

| ID | Issue | Fix |
|----|-------|-----|
| **M1** | `_norm()` duplicated in `scorer.py:17` and `flavor_profiles.py:73`. | Extract to `utils/text.py`, import in both. |
| **M2** | `wine_details` unwrap pattern (`details_raw[0] if isinstance(...)`) copied in 3 places. | Extract `_unwrap_details(raw) -> dict` to `utils/__init__.py`. |
| **M3** | `FLAVOR_VOCAB` maintained in two places (`flavor_profiles.py` and `intent.py`). | `intent.py` should `from recommendation.flavor_profiles import FLAVOR_VOCAB`. |
| **M4** | CORS `allow_origins` hardcoded to `localhost` in `main.py:16`. | Add `cors_origins: List[str]` to `Settings` with env override. |
| **M5** | Model IDs hardcoded in 4 files (`intent.py`, `extractor.py`, `claude_client.py` ×2, `somm.py`). | Add `haiku_model: str` and `sonnet_model: str` to `config.py`. |
| **M6** | `config.py` silently accepts empty API keys — fails deep in a handler, not at startup. | Make keys required or add startup validators. |
| **M7** | `config.py` uses relative `env_file = "../.env"` — breaks if server started from non-`backend/` dir. | Use `Path(__file__).parent.parent / ".env"`. |
| **M8** | `GeraldinesScraper.run_full()` reimplements `BaseScraper.run()` entirely. | Add `post_upsert_hook` callback to base class. |
| **M9** | `HebScraper._upsert_inventory_with_curbside()` duplicates base inventory upsert for one extra field. | Add `extra_fields: dict = {}` param to `BaseScraper._upsert_inventory()`. |
| **M10** | `print()` used for operational errors in `pipeline.py`, `intent.py`, `extractor.py`. | Replace with `logger.exception()` / `logger.warning()`. |

---

## Agreed First Batch [NEXT]
- **B1** — `wines.py`: `.single()` → `.maybe_single()` + 404
- **B2** — `claude_client.py`: `\uXXXX` escape handling in streaming parser
- **T1** — `claude_client.py`: test harness for the full `_gen()` state machine
- **P2** — `db.py`: Supabase module-level singletons
- **P3** — `utils/geo.py`: TTL cache on store list
- **P4** — `intent.py`, `claude_client.py`, `somm.py`, `extractor.py`: Anthropic singletons
