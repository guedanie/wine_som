"""
HEB GraphQL API probe.

The previous probe confirmed HEB calls POST https://www.heb.com/graphql
during a wine search page load. This probe:
  1. Intercepts the exact GraphQL request body + response headers
  2. Captures the full JSON response
  3. Tries to replay the same query with curl using captured headers
  4. Attempts GraphQL introspection to map the schema

Run from project root:
  python3 data/exploration/heb_graphql_probe.py
"""
import asyncio
import json
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright, Request, Response

OUT_DIR = Path(__file__).parent / "heb_probe_output"
OUT_DIR.mkdir(exist_ok=True)


async def probe():
    graphql_calls = []  # captured request + response pairs

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
            ),
        )
        page = await context.new_page()

        # Intercept GraphQL requests and their responses
        async def on_response(response: Response):
            if "graphql" in response.url.lower() and response.request.method == "POST":
                try:
                    req_body = response.request.post_data
                    resp_body = await response.text()
                    headers = dict(response.request.headers)
                    graphql_calls.append({
                        "url": response.url,
                        "status": response.status,
                        "request_headers": headers,
                        "request_body": req_body,
                        "response_body": resp_body[:3000],
                    })
                    print(f"   ★ GraphQL response captured (status {response.status})")
                except Exception as e:
                    print(f"   Could not capture GraphQL body: {e}")

        page.on("response", on_response)

        print("── Loading wine search page to trigger GraphQL calls...")
        try:
            await page.goto(
                "https://www.heb.com/search/?q=wine",
                timeout=25000,
                wait_until="domcontentloaded",
            )
        except Exception:
            pass
        await page.wait_for_timeout(5000)

        # Also try scrolling to trigger more lazy-loaded queries
        for _ in range(2):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(1500)

        await browser.close()

    # ── Save + analyze captured calls ─────────────────────────────────────────
    print(f"\n── Captured {len(graphql_calls)} GraphQL call(s)")
    (OUT_DIR / "graphql_calls.json").write_text(
        json.dumps(graphql_calls, indent=2, ensure_ascii=False)
    )
    print("   Saved → heb_probe_output/graphql_calls.json")

    for i, call in enumerate(graphql_calls):
        print(f"\n── Call {i + 1}:")
        print(f"   Status: {call['status']}")

        # Parse and pretty-print the request body
        try:
            req = json.loads(call["request_body"] or "{}")
            op_name = req.get("operationName", "(none)")
            query_preview = (req.get("query") or "")[:300].replace("\n", " ")
            variables = req.get("variables", {})
            print(f"   operationName: {op_name}")
            print(f"   variables: {json.dumps(variables)}")
            print(f"   query: {query_preview}...")
        except Exception:
            print(f"   raw body: {(call['request_body'] or '')[:300]}")

        # Parse the response
        try:
            resp = json.loads(call["response_body"])
            print(f"   response keys: {list(resp.keys())}")
            if "data" in resp:
                print(f"   data keys: {list((resp.get('data') or {}).keys())}")
                # Try to find product count
                data_str = json.dumps(resp["data"])[:500]
                print(f"   data preview: {data_str}")
        except Exception:
            print(f"   raw response: {call['response_body'][:300]}")

    # ── Try replaying the first call with curl ─────────────────────────────────
    if graphql_calls:
        print("\n── Attempting curl replay of first GraphQL call...")
        call = graphql_calls[0]
        headers = call["request_headers"]

        # Build curl command with captured headers
        curl_cmd = ["curl", "-s", "-X", "POST",
                    "https://www.heb.com/graphql",
                    "-H", "Content-Type: application/json"]

        # Add useful headers from the browser request (skip auto-managed ones)
        keep_headers = ["cookie", "authorization", "x-heb-", "user-agent", "referer", "origin"]
        for k, v in headers.items():
            if any(k.lower().startswith(h) for h in keep_headers):
                curl_cmd += ["-H", f"{k}: {v}"]

        curl_cmd += ["-d", call["request_body"] or "{}"]

        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=15)
        replay_body = result.stdout[:600]
        print(f"   curl status: (check body)")
        print(f"   response: {replay_body[:400]}")

        (OUT_DIR / "graphql_replay.json").write_text(replay_body)
        print("   Saved → heb_probe_output/graphql_replay.json")

    # ── Try GraphQL introspection ──────────────────────────────────────────────
    print("\n── Trying GraphQL introspection (schema discovery)...")
    introspection_query = json.dumps({
        "query": "{ __schema { queryType { name } types { name kind } } }"
    })
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", "https://www.heb.com/graphql",
         "-H", "Content-Type: application/json",
         "-H", "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
         "-d", introspection_query],
        capture_output=True, text=True, timeout=15
    )
    intro_body = result.stdout
    print(f"   Response: {intro_body[:500]}")
    (OUT_DIR / "graphql_introspection.json").write_text(intro_body)

    print("\n✓ Done. Files in heb_probe_output/:")
    print("  graphql_calls.json    — full intercepted requests + responses")
    print("  graphql_replay.json   — curl replay attempt")
    print("  graphql_introspection.json — schema discovery attempt")


asyncio.run(probe())
