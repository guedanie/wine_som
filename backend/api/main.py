import logging
import os
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import wines, enrichment, recommend, region, feedback, somm, search, deals

app = FastAPI(
    title="Terroir API",
    description="Wine recommendation backend",
    version="0.1.0",
)

# Production origins (e.g. the Vercel URL) via env: comma-separated list.
_extra_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"] + _extra_origins,
    # Dev convenience: any localhost port + LAN IPs (phone testing over WiFi).
    # Production origins get added via env when we deploy.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+):\d+",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(wines.router)
app.include_router(enrichment.router)
app.include_router(recommend.router)
app.include_router(region.router)
app.include_router(search.router)
app.include_router(feedback.router)
app.include_router(somm.router)
app.include_router(deals.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "terroir-api"}
