from fastapi import FastAPI
from api.routers import wines, enrichment

app = FastAPI(
    title="Terroir API",
    description="Wine recommendation backend",
    version="0.1.0",
)

app.include_router(wines.router)
app.include_router(enrichment.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "terroir-api"}
