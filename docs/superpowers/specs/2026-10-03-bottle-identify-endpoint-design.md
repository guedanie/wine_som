# Bottle identify endpoint — design

**Date:** 2026-10-03
**Status:** approved, not yet implemented

## Problem

Item 26 of the build log ("Bottle Scan") already built the two pieces of logic a photo-identification feature needs — `enrichment/label_scan.py` (Claude vision reads a label photo into structured fields) and `recommendation/label_match.py` (pure catalog-matching logic, already classifying into the five-state `scanResult` contract: `exact` / `candidates` / `vintage_mismatch` / `unstocked` / `unreadable` / `not_wine`) — but nothing wires them into a live, callable endpoint. The remaining gap, per that item's own "REMAINING before a build" list, is exactly: an `/api/identify` endpoint and a frontend. This spec covers only the endpoint.

## Scope

**In scope:** one new backend endpoint that accepts a bottle photo and returns an identification result, built for the owner to validate by hand against real photos.

**Out of scope (deliberate, per prior discussion):**
- No frontend — validated via curl/Postman against the live backend.
- No zip/nearby-store scoping — catalog-wide matching only (matches `spike_vision_match.py`'s existing approach).
- No Haiku→Sonnet fallback — Haiku only, matching its measured parity with Sonnet on top-4 recall (75% both in the existing smoke test) at lower cost/latency.
- No changes to `enrichment/label_scan.py` or `recommendation/label_match.py` — both are reused exactly as they exist today, already unit-tested.

## Design

### Endpoint

`POST /api/identify` in a new `api/routers/identify.py`, registered in `api/main.py` alongside the existing routers. Multipart file upload, field name `photo`. No auth required (matches the original design brief's "identify works signed out").

### Flow

1. Read the uploaded file's bytes and content type (reject non-image content types with a 400).
2. `enrichment.label_scan.read_label(bytes, media_type, model=HAIKU)` → `(read, meta)` — `read` is the parsed label fields or `None`; `meta` carries latency and token usage.
3. A small catalog-wide candidate fetch: token-search `wines.name`/`wines.brand` via `recommendation.candidate_filters.significant_name_tokens`, mirroring `scripts/spike_vision_match.py`'s `fetch_candidates` function. This is a NEW small function living in `api/routers/identify.py` itself (I/O glue, same pattern as `recommend.py` keeping DB calls in the router and calling into pure logic modules) — not shared with the spike script, since production routers should not import from `scripts/`, and the two are simple enough that a little duplication is cheaper than introducing a shared module for one call site each.
4. `recommendation.label_match.classify_scan(read, candidates)` → the five-state result dict. No changes to this function.
5. Return JSON: the `classify_scan` result dict, plus a `_debug` block (`{read, latency_s, model, input_tokens, output_tokens}`) — included deliberately, since this endpoint's current purpose is the owner's own manual validation, not a public contract. Revisit/strip `_debug` before any real frontend consumes this.

### Rate limiting

Reuse the existing `RateLimiter` (`api/ratelimit.py`) pattern used by `/api/recommend` and `/api/somm`. New limiter: 30/hr/IP — generous for manual testing, cheap insurance against runaway cost from a stray script or shared link.

### Error handling

- Non-image upload → 400 with a clear message, no vision call made.
- `read_label` raising (Anthropic API error, network error) → caught, logged, 502 with a generic message — matches the fail-open posture used elsewhere in this codebase (e.g. `claude_client.py`'s `stream_recommendations`), except here there's no stream to keep alive, so a clean error response is sufficient.
- Everything else (unreadable label, not-wine, unstocked, candidates, vintage mismatch) is a normal 200 — these are expected `classify_scan` outcomes, not errors.

## Testing

- Unit tests for the new candidate-fetch function (mocked Supabase client) in `tests/test_identify_api.py`, following the `httpx.AsyncClient` + `ASGITransport` pattern already used in `tests/test_somm_api.py`.
- Endpoint-level tests mocking `enrichment.label_scan.read_label` (so no real Anthropic call runs in CI) to verify: successful exact-match flow returns 200 with the right shape, a non-image upload returns 400, a `read_label` exception returns 502, rate limiting behaves per the existing limiter tests' pattern.
- No test fakes real vision accuracy — that is explicitly the owner's manual validation job against the live endpoint with real photos, not something a mocked test can measure.

## Workflow

Built on a feature branch (not `main`) — this endpoint spends real Anthropic API money on every call and is unvalidated until tested with real photos. Owner runs the backend locally, tests with real bottle photos via curl/Postman, and reports findings back in conversation for iteration. Merges to `main` via a direct commit (this project's established pattern — no PR workflow) once validated.
