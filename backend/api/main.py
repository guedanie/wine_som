import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import wines, enrichment, recommend, region, feedback, somm, search

app = FastAPI(
    title="Terroir API",
    description="Wine recommendation backend",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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


@app.get("/health")
def health():
    return {"status": "ok", "service": "terroir-api"}
