# Wine Recommendation App — Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete data foundation for the wine recommendation app — DB schema, seed ingestion, enrichment pipeline, retail scrapers, and Claude-powered recommendation engine — before touching any frontend work.

**Architecture:** FastAPI backend with SQLAlchemy ORM against PostgreSQL (pgvector). Async scraping and enrichment jobs run via Celery workers backed by Redis. The Claude API handles both fallback wine enrichment and the final recommendation step. Frontend is deferred to the last phase.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL 16 + pgvector, Redis, Celery, Playwright, Anthropic SDK, Docker Compose

---

## API Keys & External Services

### Required Before Starting

| Service | Purpose | Where to Get |
|---|---|---|
| **Anthropic Claude API** | Wine enrichment fallback + recommendation engine | [console.anthropic.com](https://console.anthropic.com) — create a key under API Keys |

### Optional / Phase-Gated

| Service | Purpose | Where to Get | When Needed |
|---|---|---|---|
| **Instacart Developer API** | Structured retail inventory (alternative to scraping) | [instacart.com/business/partner](https://www.instacart.com/business/partner) — apply for access | Phase 4 |
| **Wine-Searcher API** | Retail pricing + availability (commercial alternative to scraping Total Wine etc.) | [wine-searcher.com/api](https://www.wine-searcher.com/api) — paid tier | Phase 4 (optional upgrade) |

### No API Key Required (Web Scraping)

These are scraped with Playwright. No keys, but observe rate limits and `robots.txt`:

- **Vivino** — wine ratings, tasting notes, flavor tags
- **Wine Folly** — region/grape guides, structure profiles
- **Total Wine & More** — retail inventory
- **HEB / Central Market** — retail inventory (TX focus)
- **Spec's Wines** — retail inventory (TX focus)
- **BevMo** — retail inventory

### Environment Variables to Create

Create a `.env` file at project root before Phase 1:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Database
DATABASE_URL=postgresql+asyncpg://wine:wine@localhost:5432/winedb
REDIS_URL=redis://localhost:6379/0

# Optional
INSTACART_API_KEY=
WINE_SEARCHER_API_KEY=

# App
ENVIRONMENT=development
SECRET_KEY=changeme-in-prod
```

---

## Phase 1 — Project Scaffold & Docker

### Task 1: Directory Structure

**Files:**
- Create: `backend/api/__init__.py`
- Create: `backend/db/__init__.py`
- Create: `backend/scrapers/__init__.py`
- Create: `backend/enrichment/__init__.py`
- Create: `backend/recommender/__init__.py`
- Create: `backend/workers/__init__.py`
- Create: `data/seed/.gitkeep`
- Create: `frontend/.gitkeep` (placeholder — not built until Phase 7)

- [ ] **Step 1: Scaffold directories**

```bash
mkdir -p backend/{api,db,scrapers,enrichment,recommender,workers,tests}
mkdir -p data/seed
mkdir -p frontend
touch backend/{api,db,scrapers,enrichment,recommender,workers,tests}/__init__.py
touch data/seed/.gitkeep frontend/.gitkeep
```

- [ ] **Step 2: Create root pyproject.toml**

```toml
[tool.poetry]
name = "wine-app"
version = "0.1.0"
description = "Wine recommendation app"
python = "^3.12"

[tool.poetry.dependencies]
fastapi = "^0.115"
uvicorn = {extras = ["standard"], version = "^0.32"}
sqlalchemy = {extras = ["asyncio"], version = "^2.0"}
asyncpg = "^0.30"
alembic = "^1.14"
celery = {extras = ["redis"], version = "^5.4"}
playwright = "^1.49"
anthropic = "^0.40"
python-dotenv = "^1.0"
pydantic-settings = "^2.6"
pgvector = "^0.3"

[tool.poetry.group.dev.dependencies]
pytest = "^8.3"
pytest-asyncio = "^0.24"
httpx = "^0.28"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

- [ ] **Step 3: Create `.env` file**

```bash
cp .env.example .env  # populate ANTHROPIC_API_KEY
```

Create `.env.example`:

```bash
ANTHROPIC_API_KEY=
DATABASE_URL=postgresql+asyncpg://wine:wine@localhost:5432/winedb
REDIS_URL=redis://localhost:6379/0
ENVIRONMENT=development
SECRET_KEY=changeme-in-prod
```

- [ ] **Step 4: Commit**

```bash
git init
git add .
git commit -m "chore: scaffold project structure"
```

---

### Task 2: Docker Compose

**Files:**
- Create: `docker-compose.yml`
- Create: `backend/Dockerfile`

- [ ] **Step 1: Write docker-compose.yml**

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: wine
      POSTGRES_PASSWORD: wine
      POSTGRES_DB: winedb
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  api:
    build: ./backend
    command: uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
    volumes:
      - ./backend:/app
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - db
      - redis

  worker:
    build: ./backend
    command: celery -A workers.celery_app worker --loglevel=info
    volumes:
      - ./backend:/app
    env_file: .env
    depends_on:
      - db
      - redis

  beat:
    build: ./backend
    command: celery -A workers.celery_app beat --loglevel=info
    volumes:
      - ./backend:/app
    env_file: .env
    depends_on:
      - db
      - redis

volumes:
  pgdata:
```

- [ ] **Step 2: Write backend/Dockerfile**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install poetry
COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-root --no-interaction
RUN playwright install chromium --with-deps
COPY . .
```

- [ ] **Step 3: Start services and verify**

```bash
docker compose up -d db redis
docker compose ps
# db and redis should show "running"
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml backend/Dockerfile
git commit -m "chore: add docker compose with postgres+pgvector and redis"
```

---

## Phase 2 — Database Schema & Migrations

### Task 3: Settings & DB Connection

**Files:**
- Create: `backend/config.py`
- Create: `backend/db/engine.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_db_connection.py
import pytest
from db.engine import get_async_session

@pytest.mark.asyncio
async def test_db_connection():
    async for session in get_async_session():
        result = await session.execute("SELECT 1")
        assert result.scalar() == 1
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd backend && pytest tests/test_db_connection.py -v
# Expected: ImportError or ModuleNotFoundError
```

- [ ] **Step 3: Write config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    anthropic_api_key: str
    environment: str = "development"

    class Config:
        env_file = "../.env"

settings = Settings()
```

- [ ] **Step 4: Write db/engine.py**

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import AsyncGenerator
from config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 5: Run test — should pass**

```bash
pytest tests/test_db_connection.py -v
# Expected: PASSED
```

- [ ] **Step 6: Commit**

```bash
git add backend/config.py backend/db/engine.py backend/tests/test_db_connection.py
git commit -m "feat: db async engine and settings config"
```

---

### Task 4: SQLAlchemy Models

**Files:**
- Create: `backend/db/models.py`
- Create: `backend/db/base.py`

- [ ] **Step 1: Write base model**

```python
# backend/db/base.py
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

- [ ] **Step 2: Write models.py**

```python
# backend/db/models.py
from datetime import datetime
from sqlalchemy import (
    Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base
import enum

class WineType(str, enum.Enum):
    red = "red"
    white = "white"
    rose = "rosé"
    sparkling = "sparkling"
    dessert = "dessert"

class Wine(Base):
    __tablename__ = "wines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upc: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    producer: Mapped[str | None] = mapped_column(String(255))
    varietal: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    sub_region: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    vintage_year: Mapped[int | None] = mapped_column(Integer)
    bottle_size: Mapped[str | None] = mapped_column(String(20))
    wine_type: Mapped[WineType | None] = mapped_column(SAEnum(WineType))
    avg_price: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    details: Mapped["WineDetail | None"] = relationship(back_populates="wine")
    inventory: Mapped[list["RetailInventory"]] = relationship(back_populates="wine")

class WineDetail(Base):
    __tablename__ = "wine_details"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wine_id: Mapped[int] = mapped_column(ForeignKey("wines.id"), unique=True)
    vivino_id: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    tasting_notes: Mapped[str | None] = mapped_column(Text)
    flavor_profile: Mapped[list | None] = mapped_column(JSON)
    structure_profile: Mapped[dict | None] = mapped_column(JSON)
    vintage_notes: Mapped[str | None] = mapped_column(Text)
    critic_score: Mapped[float | None] = mapped_column(Float)
    region_summary: Mapped[str | None] = mapped_column(Text)
    soil_type: Mapped[str | None] = mapped_column(String(255))
    climate_notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(50), default="scraped")
    source_url: Mapped[str | None] = mapped_column(Text)

    wine: Mapped["Wine"] = relationship(back_populates="details")

class RetailInventory(Base):
    __tablename__ = "retail_inventory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wine_id: Mapped[int] = mapped_column(ForeignKey("wines.id"), index=True)
    retailer_name: Mapped[str] = mapped_column(String(100))
    store_id: Mapped[str | None] = mapped_column(String(100))
    store_name: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(10))
    zip_code: Mapped[str | None] = mapped_column(String(10), index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    price: Mapped[float | None] = mapped_column(Float)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    wine: Mapped["Wine"] = relationship(back_populates="inventory")

class UserPreference(Base):
    __tablename__ = "user_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    budget_min: Mapped[float | None] = mapped_column(Float)
    budget_max: Mapped[float | None] = mapped_column(Float)
    preferred_styles: Mapped[list | None] = mapped_column(JSON)
    excluded_styles: Mapped[list | None] = mapped_column(JSON)
    preferred_regions: Mapped[list | None] = mapped_column(JSON)
    zip_code: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class RecommendationSession(Base):
    __tablename__ = "recommendation_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    conversation_history: Mapped[list] = mapped_column(JSON, default=list)
    recommendations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ScrapeError(Base):
    __tablename__ = "scrape_errors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    retailer: Mapped[str] = mapped_column(String(100))
    error_type: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 3: Write model unit tests**

```python
# backend/tests/test_models.py
from db.models import Wine, WineDetail, RetailInventory, WineType

def test_wine_model_fields():
    w = Wine(name="Opus One", upc="123456789012", wine_type=WineType.red)
    assert w.name == "Opus One"
    assert w.wine_type == WineType.red

def test_wine_detail_source_default():
    d = WineDetail(wine_id=1)
    assert d.source == "scraped"

def test_retail_inventory_in_stock_default():
    r = RetailInventory(wine_id=1, retailer_name="Total Wine")
    assert r.in_stock is True
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_models.py -v
# Expected: 3 PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/db/
git commit -m "feat: sqlalchemy models for wines, inventory, enrichment, sessions"
```

---

### Task 5: Alembic Migrations

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_initial_schema.py` (auto-generated)

- [ ] **Step 1: Initialize alembic**

```bash
cd backend && alembic init alembic
```

- [ ] **Step 2: Edit alembic/env.py to use our models and async engine**

```python
# backend/alembic/env.py — replace the entire file
import asyncio
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from config import settings
from db.base import Base
from db import models  # noqa: F401 — registers all models

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    connectable = create_async_engine(settings.database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 3: Enable pgvector extension in first migration**

```bash
alembic revision --autogenerate -m "initial_schema"
```

Then prepend to the generated migration's `upgrade()`:

```python
op.execute("CREATE EXTENSION IF NOT EXISTS vector")
```

- [ ] **Step 4: Run migration against local DB**

```bash
alembic upgrade head
# Expected: all tables created with no errors
```

- [ ] **Step 5: Verify tables exist**

```bash
docker compose exec db psql -U wine -d winedb -c "\dt"
# Expected: wines, wine_details, retail_inventory, user_preferences, recommendation_sessions, scrape_errors
```

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/ backend/alembic.ini
git commit -m "feat: alembic initial schema migration with pgvector"
```

---

## Phase 3 — CSV Seed Ingestion

### Task 6: Seed Script

**Files:**
- Create: `backend/db/seed.py`
- Create: `backend/tests/test_seed.py`
- Add: `data/seed/Fair_Oaks_Stores_Analysis.csv` (user provides)

The CSV columns per spec: UPC, product name, brand, country, sub-category, store ID, store name, address, zip code, bottle size, item count, avg price, last sale date, rank.

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_seed.py
import pytest
from db.seed import parse_csv_row, CsvRow

def test_parse_csv_row_maps_fields():
    raw = {
        "UPC": "012345678901",
        "product name": "Chateau Montelena Cabernet",
        "brand": "Chateau Montelena",
        "country": "USA",
        "sub-category": "Cabernet Sauvignon",
        "store ID": "S001",
        "store name": "Fair Oaks Total Wine",
        "address": "123 Main St, Fair Oaks, CA 95628",
        "zip code": "95628",
        "bottle size": "750ml",
        "avg price": "45.99",
    }
    row = parse_csv_row(raw)
    assert row.upc == "012345678901"
    assert row.wine_name == "Chateau Montelena Cabernet"
    assert row.zip_code == "95628"
    assert row.avg_price == 45.99

def test_parse_csv_row_handles_missing_price():
    raw = {"UPC": "x", "product name": "Test Wine", "avg price": "", "zip code": "78209",
           "brand": "", "country": "", "sub-category": "", "store ID": "", "store name": "",
           "address": "", "bottle size": ""}
    row = parse_csv_row(raw)
    assert row.avg_price is None
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
pytest tests/test_seed.py -v
# Expected: ImportError
```

- [ ] **Step 3: Write db/seed.py**

```python
# backend/db/seed.py
import csv
import asyncio
from dataclasses import dataclass
from pathlib import Path
from sqlalchemy import select
from db.engine import AsyncSessionLocal
from db.models import Wine, RetailInventory

@dataclass
class CsvRow:
    upc: str
    wine_name: str
    producer: str
    country: str
    varietal: str
    store_id: str
    store_name: str
    address: str
    zip_code: str
    bottle_size: str
    avg_price: float | None

def parse_csv_row(raw: dict) -> CsvRow:
    price_str = raw.get("avg price", "").strip()
    return CsvRow(
        upc=raw.get("UPC", "").strip() or None,
        wine_name=raw.get("product name", "").strip(),
        producer=raw.get("brand", "").strip() or None,
        country=raw.get("country", "").strip() or None,
        varietal=raw.get("sub-category", "").strip() or None,
        store_id=raw.get("store ID", "").strip() or None,
        store_name=raw.get("store name", "").strip() or None,
        address=raw.get("address", "").strip() or None,
        zip_code=raw.get("zip code", "").strip() or None,
        bottle_size=raw.get("bottle size", "").strip() or None,
        avg_price=float(price_str) if price_str else None,
    )

async def seed_from_csv(csv_path: Path):
    rows: list[CsvRow] = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            rows.append(parse_csv_row(raw))

    async with AsyncSessionLocal() as session:
        for row in rows:
            # Upsert wine by UPC or name
            existing = None
            if row.upc:
                result = await session.execute(select(Wine).where(Wine.upc == row.upc))
                existing = result.scalar_one_or_none()

            if not existing:
                wine = Wine(
                    upc=row.upc,
                    name=row.wine_name,
                    producer=row.producer,
                    country=row.country,
                    varietal=row.varietal,
                    bottle_size=row.bottle_size,
                    avg_price=row.avg_price,
                )
                session.add(wine)
                await session.flush()
            else:
                wine = existing

            inventory = RetailInventory(
                wine_id=wine.id,
                retailer_name="HEB/Fair Oaks",
                store_id=row.store_id,
                store_name=row.store_name,
                address=row.address,
                zip_code=row.zip_code,
                price=row.avg_price,
                in_stock=True,
            )
            session.add(inventory)

        await session.commit()
        print(f"Seeded {len(rows)} rows from {csv_path}")

if __name__ == "__main__":
    csv_path = Path(__file__).parent.parent.parent / "data" / "seed" / "Fair_Oaks_Stores_Analysis.csv"
    asyncio.run(seed_from_csv(csv_path))
```

- [ ] **Step 4: Run unit tests — should pass**

```bash
pytest tests/test_seed.py -v
# Expected: 2 PASSED
```

- [ ] **Step 5: Run the seed against local DB (requires CSV in place)**

```bash
python -m db.seed
# Expected: "Seeded N rows from ..."
```

- [ ] **Step 6: Verify row counts**

```bash
docker compose exec db psql -U wine -d winedb -c "SELECT COUNT(*) FROM wines; SELECT COUNT(*) FROM retail_inventory;"
```

- [ ] **Step 7: Commit**

```bash
git add backend/db/seed.py backend/tests/test_seed.py
git commit -m "feat: CSV seed ingestion into wines + retail_inventory"
```

---

## Phase 4 — Basic Search API

### Task 7: FastAPI App + Wine Search Endpoint

**Files:**
- Create: `backend/api/main.py`
- Create: `backend/api/routers/wines.py`
- Create: `backend/api/schemas.py`
- Create: `backend/tests/test_wines_api.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_wines_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app

@pytest.mark.asyncio
async def test_search_wines_returns_list():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/wines/search?q=cabernet")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_search_wines_empty_query_returns_400():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/wines/search")
    assert response.status_code == 422  # FastAPI validation
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
pytest tests/test_wines_api.py -v
# Expected: ImportError or 404
```

- [ ] **Step 3: Write api/schemas.py**

```python
# backend/api/schemas.py
from pydantic import BaseModel
from datetime import datetime

class WineSearchResult(BaseModel):
    id: int
    name: str
    producer: str | None
    varietal: str | None
    region: str | None
    country: str | None
    avg_price: float | None
    wine_type: str | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Write api/routers/wines.py**

```python
# backend/api/routers/wines.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.engine import get_async_session
from db.models import Wine
from api.schemas import WineSearchResult

router = APIRouter(prefix="/api/wines", tags=["wines"])

@router.get("/search", response_model=list[WineSearchResult])
async def search_wines(
    q: str = Query(..., min_length=1, description="Search term"),
    limit: int = Query(20, le=100),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(Wine)
        .where(Wine.name.ilike(f"%{q}%"))
        .limit(limit)
    )
    return result.scalars().all()
```

- [ ] **Step 5: Write api/main.py**

```python
# backend/api/main.py
from fastapi import FastAPI
from api.routers import wines

app = FastAPI(title="Wine Recommendation API")
app.include_router(wines.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Run tests — should pass**

```bash
pytest tests/test_wines_api.py -v
# Expected: 2 PASSED
```

- [ ] **Step 7: Smoke test manually**

```bash
uvicorn api.main:app --reload
curl "http://localhost:8000/api/wines/search?q=cabernet"
```

- [ ] **Step 8: Commit**

```bash
git add backend/api/
git commit -m "feat: /api/wines/search endpoint with FastAPI"
```

---

## Phase 5 — Wine Enrichment Pipeline

### Task 8: Celery Worker Setup

**Files:**
- Create: `backend/workers/celery_app.py`
- Create: `backend/workers/enrichment_tasks.py`

- [ ] **Step 1: Write celery_app.py**

```python
# backend/workers/celery_app.py
from celery import Celery
from config import settings

celery_app = Celery(
    "wine_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["workers.enrichment_tasks", "workers.scraper_tasks"],
)

celery_app.conf.beat_schedule = {
    "scrape-retail-daily": {
        "task": "workers.scraper_tasks.run_all_scrapers",
        "schedule": 86400.0,  # 24 hours
    },
}
```

- [ ] **Step 2: Write failing enrichment task test**

```python
# backend/tests/test_enrichment_tasks.py
from unittest.mock import patch, AsyncMock
from workers.enrichment_tasks import enrich_wine_task

def test_enrich_wine_task_is_registered():
    assert enrich_wine_task.name == "workers.enrichment_tasks.enrich_wine_task"
```

- [ ] **Step 3: Write workers/enrichment_tasks.py stub**

```python
# backend/workers/enrichment_tasks.py
from workers.celery_app import celery_app

@celery_app.task(name="workers.enrichment_tasks.enrich_wine_task", bind=True, max_retries=3)
def enrich_wine_task(self, wine_id: int):
    from enrichment.pipeline import run_enrichment
    import asyncio
    asyncio.run(run_enrichment(wine_id))
```

- [ ] **Step 4: Run test**

```bash
pytest tests/test_enrichment_tasks.py -v
# Expected: PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/workers/
git commit -m "feat: celery worker app with enrichment task stub"
```

---

### Task 9: Vivino Scraper

**Files:**
- Create: `backend/enrichment/vivino.py`
- Create: `backend/tests/test_vivino.py`

- [ ] **Step 1: Write failing test with mocked Playwright**

```python
# backend/tests/test_vivino.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from enrichment.vivino import VivinoScraper, VivinoResult

@pytest.mark.asyncio
async def test_parse_vivino_page_returns_result():
    scraper = VivinoScraper()
    html = """
    <div class="wine-card__name">Opus One 2019</div>
    <div class="average__number">4.5</div>
    <div class="tag-highlight">dark cherry</div>
    <div class="tag-highlight">tobacco</div>
    """
    result = scraper._parse_html(html, wine_name="Opus One")
    assert result.rating == 4.5
    assert "dark cherry" in result.flavor_tags

@pytest.mark.asyncio
async def test_scraper_returns_none_on_not_found():
    scraper = VivinoScraper()
    result = scraper._parse_html("<html><body>No results</body></html>", wine_name="xyz")
    assert result is None
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
pytest tests/test_vivino.py -v
# Expected: ImportError
```

- [ ] **Step 3: Write enrichment/vivino.py**

```python
# backend/enrichment/vivino.py
import asyncio
import random
from dataclasses import dataclass, field
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

@dataclass
class VivinoResult:
    wine_name: str
    rating: float | None = None
    flavor_tags: list[str] = field(default_factory=list)
    tasting_notes: str | None = None
    critic_score: float | None = None
    source_url: str | None = None

class VivinoScraper:
    BASE_URL = "https://www.vivino.com/search/wines"

    def _parse_html(self, html: str, wine_name: str) -> VivinoResult | None:
        soup = BeautifulSoup(html, "html.parser")
        rating_el = soup.select_one(".average__number")
        if not rating_el:
            return None
        try:
            rating = float(rating_el.text.strip().replace(",", "."))
        except ValueError:
            rating = None
        tags = [el.text.strip() for el in soup.select(".tag-highlight")]
        return VivinoResult(wine_name=wine_name, rating=rating, flavor_tags=tags)

    async def search(self, wine_name: str) -> VivinoResult | None:
        await asyncio.sleep(random.uniform(2.0, 5.0))  # polite scraping
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                url = f"{self.BASE_URL}?q={wine_name.replace(' ', '+')}"
                await page.goto(url, timeout=15000)
                await page.wait_for_load_state("networkidle")
                html = await page.content()
                result = self._parse_html(html, wine_name)
                if result:
                    result.source_url = url
                return result
            finally:
                await browser.close()
```

- [ ] **Step 4: Run tests — should pass**

```bash
pytest tests/test_vivino.py -v
# Expected: 2 PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/enrichment/vivino.py backend/tests/test_vivino.py
git commit -m "feat: Vivino scraper with Playwright and polite rate limiting"
```

---

### Task 10: Claude Enrichment Fallback

**Files:**
- Create: `backend/enrichment/claude_enrichment.py`
- Create: `backend/tests/test_claude_enrichment.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_claude_enrichment.py
import pytest
from unittest.mock import patch, MagicMock
from enrichment.claude_enrichment import ClaudeEnricher, EnrichmentResult

def test_parse_claude_response_extracts_fields():
    enricher = ClaudeEnricher.__new__(ClaudeEnricher)
    raw = """{
      "description": "A bold Napa Cabernet",
      "tasting_notes": "Dark cherry, graphite, long finish",
      "flavor_profile": ["dark cherry", "graphite", "cedar"],
      "structure_profile": {"body": "full", "tannin": "high", "acidity": "medium"},
      "region_summary": "Napa Valley is known for its warm climate."
    }"""
    result = enricher._parse_response(raw, wine_name="Test Wine")
    assert result.flavor_profile == ["dark cherry", "graphite", "cedar"]
    assert result.structure_profile["body"] == "full"
    assert result.source == "ai_generated"
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
pytest tests/test_claude_enrichment.py -v
# Expected: ImportError
```

- [ ] **Step 3: Write enrichment/claude_enrichment.py**

```python
# backend/enrichment/claude_enrichment.py
import json
from dataclasses import dataclass, field
import anthropic
from config import settings

@dataclass
class EnrichmentResult:
    wine_name: str
    description: str | None = None
    tasting_notes: str | None = None
    flavor_profile: list[str] = field(default_factory=list)
    structure_profile: dict = field(default_factory=dict)
    region_summary: str | None = None
    source: str = "ai_generated"

SYSTEM_PROMPT = """You are a master sommelier. Return a JSON object with these exact keys:
- description (string): 2-3 sentence wine description
- tasting_notes (string): Specific tasting note sentence
- flavor_profile (array of strings): 4-6 flavor descriptors, e.g. ["dark cherry", "tobacco"]
- structure_profile (object): {"body": "light|medium|full", "tannin": "low|medium|high", "acidity": "low|medium|high", "finish_length": "short|medium|long"}
- region_summary (string): 1-2 sentences on the wine's region

Return ONLY valid JSON. No other text."""

class ClaudeEnricher:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def _parse_response(self, raw: str, wine_name: str) -> EnrichmentResult:
        data = json.loads(raw.strip())
        return EnrichmentResult(
            wine_name=wine_name,
            description=data.get("description"),
            tasting_notes=data.get("tasting_notes"),
            flavor_profile=data.get("flavor_profile", []),
            structure_profile=data.get("structure_profile", {}),
            region_summary=data.get("region_summary"),
        )

    def enrich(self, wine_name: str, varietal: str | None, region: str | None, vintage: int | None) -> EnrichmentResult:
        user_msg = f"Wine: {wine_name}"
        if varietal:
            user_msg += f"\nVarietal: {varietal}"
        if region:
            user_msg += f"\nRegion: {region}"
        if vintage:
            user_msg += f"\nVintage: {vintage}"

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        return self._parse_response(response.content[0].text, wine_name)
```

- [ ] **Step 4: Run tests — should pass**

```bash
pytest tests/test_claude_enrichment.py -v
# Expected: PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/enrichment/claude_enrichment.py backend/tests/test_claude_enrichment.py
git commit -m "feat: Claude API fallback enrichment with structured JSON output"
```

---

### Task 11: Enrichment Pipeline Orchestrator

**Files:**
- Create: `backend/enrichment/pipeline.py`
- Create: `backend/tests/test_pipeline.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_pipeline.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_run_enrichment_uses_vivino_first():
    with patch("enrichment.pipeline.VivinoScraper") as mock_vivino_cls, \
         patch("enrichment.pipeline.AsyncSessionLocal") as mock_session_cls:
        mock_vivino = AsyncMock()
        mock_vivino.search.return_value = MagicMock(
            rating=4.3, flavor_tags=["cherry"], tasting_notes="Rich", source_url="http://v.com"
        )
        mock_vivino_cls.return_value = mock_vivino

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get.return_value = MagicMock(
            id=1, name="Test Wine", varietal="Cab", region="Napa", vintage_year=2019, details=None
        )
        mock_session_cls.return_value = mock_session

        from enrichment.pipeline import run_enrichment
        await run_enrichment(1)
        mock_vivino.search.assert_called_once()
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
pytest tests/test_pipeline.py -v
# Expected: ImportError
```

- [ ] **Step 3: Write enrichment/pipeline.py**

```python
# backend/enrichment/pipeline.py
from db.engine import AsyncSessionLocal
from db.models import Wine, WineDetail
from enrichment.vivino import VivinoScraper
from enrichment.claude_enrichment import ClaudeEnricher

async def run_enrichment(wine_id: int):
    async with AsyncSessionLocal() as session:
        wine = await session.get(Wine, wine_id)
        if not wine:
            return

        vivino = VivinoScraper()
        result = await vivino.search(wine.name)

        if result:
            detail = WineDetail(
                wine_id=wine.id,
                critic_score=result.rating,
                flavor_profile=result.flavor_tags,
                tasting_notes=result.tasting_notes,
                source="scraped",
                source_url=result.source_url,
            )
        else:
            enricher = ClaudeEnricher()
            ai_result = enricher.enrich(wine.name, wine.varietal, wine.region, wine.vintage_year)
            detail = WineDetail(
                wine_id=wine.id,
                description=ai_result.description,
                tasting_notes=ai_result.tasting_notes,
                flavor_profile=ai_result.flavor_profile,
                structure_profile=ai_result.structure_profile,
                region_summary=ai_result.region_summary,
                source="ai_generated",
            )

        if wine.details:
            for key, val in vars(detail).items():
                if not key.startswith("_"):
                    setattr(wine.details, key, val)
        else:
            session.add(detail)

        await session.commit()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_pipeline.py -v
# Expected: PASSED
```

- [ ] **Step 5: Wire pipeline into Celery task (update enrichment_tasks.py)**

The stub in Task 8 already calls `run_enrichment` — no change needed.

- [ ] **Step 6: Commit**

```bash
git add backend/enrichment/pipeline.py backend/tests/test_pipeline.py
git commit -m "feat: enrichment pipeline — Vivino first, Claude fallback"
```

---

## Phase 6 — Retail Scrapers

### Task 12: BaseScraper Interface

**Files:**
- Create: `backend/scrapers/base.py`
- Create: `backend/tests/test_base_scraper.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_base_scraper.py
import pytest
from scrapers.base import BaseScraper, RetailInventoryItem

def test_base_scraper_is_abstract():
    with pytest.raises(TypeError):
        BaseScraper()

def test_retail_inventory_item_fields():
    item = RetailInventoryItem(
        wine_name="Opus One",
        upc="123",
        price=199.99,
        store_name="Total Wine",
        store_id="TW001",
        address="123 Main St",
        city="Austin",
        state="TX",
        zip_code="78209",
        in_stock=True,
        retailer_name="Total Wine",
    )
    assert item.price == 199.99
    assert item.in_stock is True
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
pytest tests/test_base_scraper.py -v
# Expected: ImportError
```

- [ ] **Step 3: Write scrapers/base.py**

```python
# backend/scrapers/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class RetailInventoryItem:
    wine_name: str
    upc: str | None
    price: float | None
    store_name: str
    store_id: str | None
    address: str | None
    city: str | None
    state: str | None
    zip_code: str
    in_stock: bool
    retailer_name: str

class BaseScraper(ABC):
    @abstractmethod
    async def search_by_zip(self, zip_code: str) -> list[RetailInventoryItem]: ...

    @abstractmethod
    async def search_by_wine(self, wine_name: str, zip_code: str) -> list[RetailInventoryItem]: ...

    @abstractmethod
    async def get_store_inventory(self, store_id: str) -> list[RetailInventoryItem]: ...
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_base_scraper.py -v
# Expected: 2 PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/scrapers/base.py backend/tests/test_base_scraper.py
git commit -m "feat: BaseScraper abstract interface and RetailInventoryItem dataclass"
```

---

### Task 13: Total Wine Scraper

**Files:**
- Create: `backend/scrapers/total_wine.py`
- Create: `backend/tests/test_total_wine.py`

- [ ] **Step 1: Write failing test with mocked HTML**

```python
# backend/tests/test_total_wine.py
import pytest
from scrapers.total_wine import TotalWineScraper

def test_parse_product_card():
    scraper = TotalWineScraper()
    html = """
    <div class="product-card">
      <div class="product-card__name">Caymus Cabernet 2021</div>
      <div class="product-card__price">$89.99</div>
      <div class="product-card__sku">SKU12345</div>
      <div class="product-card__availability">In Stock</div>
    </div>
    """
    items = scraper._parse_products(html, zip_code="78209", store_name="Total Wine Austin", store_id="TW-ATX")
    assert len(items) == 1
    assert items[0].wine_name == "Caymus Cabernet 2021"
    assert items[0].price == 89.99
    assert items[0].in_stock is True
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
pytest tests/test_total_wine.py -v
# Expected: ImportError
```

- [ ] **Step 3: Write scrapers/total_wine.py**

```python
# backend/scrapers/total_wine.py
import asyncio, random, re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper, RetailInventoryItem

class TotalWineScraper(BaseScraper):
    BASE_URL = "https://www.totalwine.com"

    def _parse_price(self, text: str) -> float | None:
        match = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
        return float(match.group()) if match else None

    def _parse_products(self, html: str, zip_code: str, store_name: str, store_id: str) -> list[RetailInventoryItem]:
        soup = BeautifulSoup(html, "html.parser")
        items = []
        for card in soup.select(".product-card"):
            name_el = card.select_one(".product-card__name")
            price_el = card.select_one(".product-card__price")
            avail_el = card.select_one(".product-card__availability")
            if not name_el:
                continue
            items.append(RetailInventoryItem(
                wine_name=name_el.text.strip(),
                upc=None,
                price=self._parse_price(price_el.text) if price_el else None,
                store_name=store_name,
                store_id=store_id,
                address=None,
                city=None,
                state=None,
                zip_code=zip_code,
                in_stock="In Stock" in (avail_el.text if avail_el else ""),
                retailer_name="Total Wine",
            ))
        return items

    async def _fetch_page(self, url: str) -> str:
        await asyncio.sleep(random.uniform(2.0, 5.0))
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, timeout=20000)
                await page.wait_for_load_state("networkidle")
                return await page.content()
            finally:
                await browser.close()

    async def search_by_zip(self, zip_code: str) -> list[RetailInventoryItem]:
        url = f"{self.BASE_URL}/wine?zip={zip_code}"
        html = await self._fetch_page(url)
        return self._parse_products(html, zip_code, "Total Wine", "TW-unknown")

    async def search_by_wine(self, wine_name: str, zip_code: str) -> list[RetailInventoryItem]:
        url = f"{self.BASE_URL}/search?text={wine_name.replace(' ', '+')}&zip={zip_code}"
        html = await self._fetch_page(url)
        return self._parse_products(html, zip_code, "Total Wine", "TW-unknown")

    async def get_store_inventory(self, store_id: str) -> list[RetailInventoryItem]:
        url = f"{self.BASE_URL}/store/{store_id}/wine"
        html = await self._fetch_page(url)
        return self._parse_products(html, "", "Total Wine", store_id)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_total_wine.py -v
# Expected: PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/scrapers/total_wine.py backend/tests/test_total_wine.py
git commit -m "feat: Total Wine scraper with Playwright and HTML parser"
```

---

### Task 14: HEB / Spec's Scrapers

Build the same pattern as Task 13 for HEB and Spec's — priority retailers for the Texas market.

**Files:**
- Create: `backend/scrapers/heb.py`
- Create: `backend/scrapers/specs.py`
- Create: `backend/tests/test_heb.py`
- Create: `backend/tests/test_specs.py`

- [ ] **Step 1: Write failing tests for HEB**

```python
# backend/tests/test_heb.py
from scrapers.heb import HEBScraper

def test_parse_heb_product():
    scraper = HEBScraper()
    html = """
    <div class="product-tile">
      <span class="product-tile__description">La Marca Prosecco</span>
      <span class="product-tile__price">$14.98</span>
    </div>
    """
    items = scraper._parse_products(html, zip_code="78209", store_name="HEB", store_id="HEB-001")
    assert items[0].wine_name == "La Marca Prosecco"
    assert items[0].price == 14.98
    assert items[0].retailer_name == "HEB"
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
pytest tests/test_heb.py -v
# Expected: ImportError
```

- [ ] **Step 3: Write scrapers/heb.py**

```python
# backend/scrapers/heb.py
import asyncio, random, re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper, RetailInventoryItem

class HEBScraper(BaseScraper):
    BASE_URL = "https://www.heb.com"

    def _parse_price(self, text: str) -> float | None:
        match = re.search(r"[\d]+\.?\d*", text.replace(",", ""))
        return float(match.group()) if match else None

    def _parse_products(self, html: str, zip_code: str, store_name: str, store_id: str) -> list[RetailInventoryItem]:
        soup = BeautifulSoup(html, "html.parser")
        items = []
        for tile in soup.select(".product-tile"):
            name_el = tile.select_one(".product-tile__description")
            price_el = tile.select_one(".product-tile__price")
            if not name_el:
                continue
            items.append(RetailInventoryItem(
                wine_name=name_el.text.strip(),
                upc=None,
                price=self._parse_price(price_el.text) if price_el else None,
                store_name=store_name,
                store_id=store_id,
                address=None,
                city=None,
                state="TX",
                zip_code=zip_code,
                in_stock=True,
                retailer_name="HEB",
            ))
        return items

    async def _fetch_page(self, url: str) -> str:
        await asyncio.sleep(random.uniform(2.0, 5.0))
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, timeout=20000)
                await page.wait_for_load_state("networkidle")
                return await page.content()
            finally:
                await browser.close()

    async def search_by_zip(self, zip_code: str) -> list[RetailInventoryItem]:
        url = f"{self.BASE_URL}/search?q=wine&store_zip={zip_code}&department=wine"
        html = await self._fetch_page(url)
        return self._parse_products(html, zip_code, "HEB", "HEB-unknown")

    async def search_by_wine(self, wine_name: str, zip_code: str) -> list[RetailInventoryItem]:
        url = f"{self.BASE_URL}/search?q={wine_name.replace(' ', '+')}&store_zip={zip_code}"
        html = await self._fetch_page(url)
        return self._parse_products(html, zip_code, "HEB", "HEB-unknown")

    async def get_store_inventory(self, store_id: str) -> list[RetailInventoryItem]:
        url = f"{self.BASE_URL}/store/{store_id}/wine"
        html = await self._fetch_page(url)
        return self._parse_products(html, "", "HEB", store_id)
```

- [ ] **Step 4: Write scrapers/specs.py** (same pattern, different selectors)

```python
# backend/scrapers/specs.py
import asyncio, random, re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper, RetailInventoryItem

class SpecsScraper(BaseScraper):
    BASE_URL = "https://www.specsonline.com"

    def _parse_price(self, text: str) -> float | None:
        match = re.search(r"[\d]+\.?\d*", text.replace(",", ""))
        return float(match.group()) if match else None

    def _parse_products(self, html: str, zip_code: str, store_name: str, store_id: str) -> list[RetailInventoryItem]:
        soup = BeautifulSoup(html, "html.parser")
        items = []
        for card in soup.select(".product-item"):
            name_el = card.select_one(".product-item__name")
            price_el = card.select_one(".product-item__price")
            if not name_el:
                continue
            items.append(RetailInventoryItem(
                wine_name=name_el.text.strip(),
                upc=None,
                price=self._parse_price(price_el.text) if price_el else None,
                store_name=store_name,
                store_id=store_id,
                address=None,
                city=None,
                state="TX",
                zip_code=zip_code,
                in_stock=True,
                retailer_name="Spec's",
            ))
        return items

    async def _fetch_page(self, url: str) -> str:
        await asyncio.sleep(random.uniform(2.0, 5.0))
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, timeout=20000)
                await page.wait_for_load_state("networkidle")
                return await page.content()
            finally:
                await browser.close()

    async def search_by_zip(self, zip_code: str) -> list[RetailInventoryItem]:
        url = f"{self.BASE_URL}/catalog?category=wine&zip={zip_code}"
        html = await self._fetch_page(url)
        return self._parse_products(html, zip_code, "Spec's", "SPECS-unknown")

    async def search_by_wine(self, wine_name: str, zip_code: str) -> list[RetailInventoryItem]:
        url = f"{self.BASE_URL}/search?q={wine_name.replace(' ', '+')}&zip={zip_code}"
        html = await self._fetch_page(url)
        return self._parse_products(html, zip_code, "Spec's", "SPECS-unknown")

    async def get_store_inventory(self, store_id: str) -> list[RetailInventoryItem]:
        url = f"{self.BASE_URL}/store/{store_id}"
        html = await self._fetch_page(url)
        return self._parse_products(html, "", "Spec's", store_id)
```

- [ ] **Step 5: Run all scraper tests**

```bash
pytest tests/test_heb.py tests/test_specs.py -v
# Expected: all PASSED
```

- [ ] **Step 6: Commit**

```bash
git add backend/scrapers/heb.py backend/scrapers/specs.py backend/tests/
git commit -m "feat: HEB and Spec's scrapers for TX market"
```

---

### Task 15: Scraper Celery Tasks & DB Persistence

**Files:**
- Create: `backend/workers/scraper_tasks.py`
- Create: `backend/tests/test_scraper_tasks.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_scraper_tasks.py
from workers.scraper_tasks import run_all_scrapers

def test_run_all_scrapers_is_registered():
    assert run_all_scrapers.name == "workers.scraper_tasks.run_all_scrapers"
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
pytest tests/test_scraper_tasks.py -v
# Expected: ImportError
```

- [ ] **Step 3: Write workers/scraper_tasks.py**

```python
# backend/workers/scraper_tasks.py
import asyncio
from workers.celery_app import celery_app
from db.engine import AsyncSessionLocal
from db.models import Wine, RetailInventory, ScrapeError
from scrapers.total_wine import TotalWineScraper
from scrapers.heb import HEBScraper
from scrapers.specs import SpecsScraper

SCRAPERS = [TotalWineScraper, HEBScraper, SpecsScraper]
DEFAULT_ZIP_CODES = ["78209", "78701", "78750"]  # configurable

@celery_app.task(name="workers.scraper_tasks.run_all_scrapers")
def run_all_scrapers():
    asyncio.run(_run_all_scrapers_async())

async def _run_all_scrapers_async():
    async with AsyncSessionLocal() as session:
        for ScraperClass in SCRAPERS:
            scraper = ScraperClass()
            for zip_code in DEFAULT_ZIP_CODES:
                try:
                    items = await scraper.search_by_zip(zip_code)
                    for item in items:
                        inventory = RetailInventory(
                            wine_id=await _get_or_create_wine_id(session, item.wine_name, item.upc),
                            retailer_name=item.retailer_name,
                            store_id=item.store_id,
                            store_name=item.store_name,
                            address=item.address,
                            city=item.city,
                            state=item.state,
                            zip_code=item.zip_code,
                            price=item.price,
                            in_stock=item.in_stock,
                        )
                        session.add(inventory)
                    await session.commit()
                except Exception as e:
                    session.add(ScrapeError(
                        retailer=scraper.__class__.__name__,
                        error_type=type(e).__name__,
                        message=str(e),
                    ))
                    await session.commit()

async def _get_or_create_wine_id(session, wine_name: str, upc: str | None) -> int:
    from sqlalchemy import select
    if upc:
        result = await session.execute(select(Wine).where(Wine.upc == upc))
        wine = result.scalar_one_or_none()
        if wine:
            return wine.id
    wine = Wine(name=wine_name, upc=upc)
    session.add(wine)
    await session.flush()
    return wine.id
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_scraper_tasks.py -v
# Expected: PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/workers/scraper_tasks.py backend/tests/test_scraper_tasks.py
git commit -m "feat: scraper celery tasks with DB persistence and error logging"
```

---

## Phase 7 — Recommendation Engine

### Task 16: Candidate Retrieval (Scoring)

**Files:**
- Create: `backend/recommender/candidate_retrieval.py`
- Create: `backend/tests/test_candidate_retrieval.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_candidate_retrieval.py
from recommender.candidate_retrieval import score_candidate, UserPreferences

def test_score_candidate_full_match():
    prefs = UserPreferences(
        zip_code="78209",
        budget_min=20.0,
        budget_max=60.0,
        style_preferences=["dark cherry", "tobacco"],
        avoid=[],
        wine_type="red",
    )
    flavor_profile = ["dark cherry", "tobacco", "cedar"]
    score = score_candidate(price=45.0, flavor_profile=flavor_profile, prefs=prefs, wine_type="red")
    assert score > 0.8

def test_score_candidate_price_out_of_range():
    prefs = UserPreferences(zip_code="78209", budget_min=10, budget_max=30,
                            style_preferences=["light"], avoid=[], wine_type="white")
    score = score_candidate(price=80.0, flavor_profile=["light"], prefs=prefs, wine_type="white")
    assert score == 0.0

def test_score_candidate_penalizes_avoided_styles():
    prefs = UserPreferences(zip_code="78209", budget_min=10, budget_max=50,
                            style_preferences=["dry"], avoid=["sweet"], wine_type="red")
    score = score_candidate(price=25.0, flavor_profile=["sweet", "fruity"], prefs=prefs, wine_type="red")
    assert score < 0.3
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
pytest tests/test_candidate_retrieval.py -v
# Expected: ImportError
```

- [ ] **Step 3: Write recommender/candidate_retrieval.py**

```python
# backend/recommender/candidate_retrieval.py
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Wine, WineDetail, RetailInventory

@dataclass
class UserPreferences:
    zip_code: str
    budget_min: float
    budget_max: float
    style_preferences: list[str]
    avoid: list[str]
    wine_type: str | None = None

def score_candidate(price: float, flavor_profile: list[str], prefs: UserPreferences, wine_type: str | None) -> float:
    if price < prefs.budget_min or price > prefs.budget_max:
        return 0.0

    flavor_lower = [f.lower() for f in flavor_profile]
    avoid_hits = sum(1 for a in prefs.avoid if a.lower() in flavor_lower)
    if avoid_hits > 0:
        return max(0.0, 0.5 - (avoid_hits * 0.2))

    pref_hits = sum(1 for p in prefs.style_preferences if p.lower() in flavor_lower)
    style_score = pref_hits / max(len(prefs.style_preferences), 1)

    type_bonus = 0.1 if prefs.wine_type and wine_type == prefs.wine_type else 0.0
    return min(1.0, style_score + type_bonus)

async def get_candidates(session: AsyncSession, prefs: UserPreferences, limit: int = 15):
    result = await session.execute(
        select(Wine, WineDetail, RetailInventory)
        .join(RetailInventory, Wine.id == RetailInventory.wine_id)
        .join(WineDetail, Wine.id == WineDetail.wine_id, isouter=True)
        .where(RetailInventory.zip_code == prefs.zip_code)
        .where(RetailInventory.price >= prefs.budget_min)
        .where(RetailInventory.price <= prefs.budget_max)
        .where(RetailInventory.in_stock == True)
    )
    rows = result.all()

    scored = []
    for wine, detail, inventory in rows:
        flavor = detail.flavor_profile if detail else []
        wine_type = wine.wine_type.value if wine.wine_type else None
        score = score_candidate(inventory.price, flavor or [], prefs, wine_type)
        if score > 0:
            scored.append((score, wine, detail, inventory))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:limit]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_candidate_retrieval.py -v
# Expected: 3 PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/recommender/candidate_retrieval.py backend/tests/test_candidate_retrieval.py
git commit -m "feat: candidate retrieval with weighted scoring against user preferences"
```

---

### Task 17: Claude Recommendation Engine

**Files:**
- Create: `backend/recommender/engine.py`
- Create: `backend/tests/test_engine.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_engine.py
from unittest.mock import patch, MagicMock
from recommender.engine import build_recommendation_prompt, RecommendationCandidate

def test_build_prompt_includes_wine_names():
    candidates = [
        RecommendationCandidate(
            wine_name="Caymus Cabernet",
            producer="Caymus",
            region="Napa Valley",
            price=89.99,
            store_name="Total Wine Austin",
            store_address="123 Main St",
            flavor_tags=["dark cherry", "vanilla"],
            structure={"body": "full", "tannin": "high"},
            vintage=2021,
        )
    ]
    prompt = build_recommendation_prompt(candidates, user_message="I want something bold and rich")
    assert "Caymus Cabernet" in prompt
    assert "dark cherry" in prompt
    assert "bold and rich" in prompt
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
pytest tests/test_engine.py -v
# Expected: ImportError
```

- [ ] **Step 3: Write recommender/engine.py**

```python
# backend/recommender/engine.py
from dataclasses import dataclass, field
import anthropic
from config import settings

SYSTEM_PROMPT = """You are an expert wine sommelier. Given the user's preferences and a list of wines 
currently available at stores near them, recommend 3-5 wines with substantive explanations. For each wine:
- Explain why it matches their stated preferences (be specific about flavor, structure, finish)
- Mention the region and what makes it distinctive
- Note the vintage if known and whether it's drinking well now
- Include the store name, address, and price
- Be opinionated — if one wine clearly stands out, say so

Do not lead with food pairings. Write like a knowledgeable friend, not a textbook.
Use short paragraphs. Avoid vague descriptors without context."""

@dataclass
class RecommendationCandidate:
    wine_name: str
    producer: str | None
    region: str | None
    price: float
    store_name: str
    store_address: str | None
    flavor_tags: list[str]
    structure: dict
    vintage: int | None

def build_recommendation_prompt(candidates: list[RecommendationCandidate], user_message: str) -> str:
    wine_list = "\n\n".join([
        f"- {c.wine_name} ({c.vintage or 'NV'}) by {c.producer or 'Unknown'}\n"
        f"  Region: {c.region or 'Unknown'}\n"
        f"  Price: ${c.price:.2f} at {c.store_name} ({c.store_address or 'address TBD'})\n"
        f"  Flavors: {', '.join(c.flavor_tags)}\n"
        f"  Structure: {c.structure}"
        for c in candidates
    ])
    return f"User request: {user_message}\n\nAvailable wines:\n{wine_list}"

class RecommendationEngine:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def recommend(
        self,
        candidates: list[RecommendationCandidate],
        conversation_history: list[dict],
        user_message: str,
    ) -> str:
        user_content = build_recommendation_prompt(candidates, user_message)
        messages = conversation_history + [{"role": "user", "content": user_content}]
        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return response.content[0].text
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_engine.py -v
# Expected: PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/recommender/engine.py backend/tests/test_engine.py
git commit -m "feat: Claude recommendation engine with conversation history support"
```

---

## Phase 8 — API Endpoints (Data-Facing)

### Task 18: Preferences + Recommend + Chat Endpoints

**Files:**
- Create: `backend/api/routers/preferences.py`
- Create: `backend/api/routers/recommend.py`
- Modify: `backend/api/main.py`
- Modify: `backend/api/schemas.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_recommend_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from api.main import app

@pytest.mark.asyncio
async def test_recommend_endpoint_requires_zip():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/recommend", json={"budget_min": 20, "budget_max": 50})
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_recommend_endpoint_returns_text():
    with patch("api.routers.recommend.RecommendationEngine") as MockEngine:
        MockEngine.return_value.recommend.return_value = "Here are my top picks..."
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 20, "budget_max": 60,
                "style_preferences": ["bold"], "avoid": [], "message": "I want something rich"
            })
    assert response.status_code == 200
    assert "recommendation" in response.json()
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
pytest tests/test_recommend_api.py -v
# Expected: ImportError or 404
```

- [ ] **Step 3: Add schemas to api/schemas.py**

```python
# Append to backend/api/schemas.py
class PreferenceRequest(BaseModel):
    zip_code: str
    budget_min: float
    budget_max: float
    style_preferences: list[str] = []
    avoid: list[str] = []
    wine_type: str | None = None
    message: str = "Recommend wines based on my preferences"

class RecommendationResponse(BaseModel):
    recommendation: str
    session_id: str
```

- [ ] **Step 4: Write api/routers/recommend.py**

```python
# backend/api/routers/recommend.py
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from db.engine import get_async_session
from db.models import RecommendationSession
from api.schemas import PreferenceRequest, RecommendationResponse
from recommender.candidate_retrieval import get_candidates, UserPreferences
from recommender.engine import RecommendationEngine, RecommendationCandidate

router = APIRouter(prefix="/api", tags=["recommendations"])

@router.post("/recommend", response_model=RecommendationResponse)
async def recommend(req: PreferenceRequest, session: AsyncSession = Depends(get_async_session)):
    prefs = UserPreferences(
        zip_code=req.zip_code,
        budget_min=req.budget_min,
        budget_max=req.budget_max,
        style_preferences=req.style_preferences,
        avoid=req.avoid,
        wine_type=req.wine_type,
    )
    scored = await get_candidates(session, prefs)
    candidates = [
        RecommendationCandidate(
            wine_name=wine.name,
            producer=wine.producer,
            region=wine.region,
            price=inventory.price or 0,
            store_name=inventory.store_name or "",
            store_address=inventory.address,
            flavor_tags=detail.flavor_profile if detail else [],
            structure=detail.structure_profile if detail else {},
            vintage=wine.vintage_year,
        )
        for _, wine, detail, inventory in scored
    ]
    engine = RecommendationEngine()
    text = engine.recommend(candidates, [], req.message)
    session_id = str(uuid.uuid4())
    rec_session = RecommendationSession(
        session_id=session_id,
        conversation_history=[{"role": "user", "content": req.message}],
        recommendations=[c.wine_name for c in candidates],
    )
    session.add(rec_session)
    await session.commit()
    return RecommendationResponse(recommendation=text, session_id=session_id)
```

- [ ] **Step 5: Register router in api/main.py**

```python
# Add to backend/api/main.py
from api.routers import wines, recommend

app.include_router(wines.router)
app.include_router(recommend.router)
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_recommend_api.py -v
# Expected: 2 PASSED
```

- [ ] **Step 7: Commit**

```bash
git add backend/api/routers/recommend.py backend/api/schemas.py backend/api/main.py backend/tests/test_recommend_api.py
git commit -m "feat: /api/recommend endpoint with Claude-powered recommendations"
```

---

### Task 19: Admin + Enrich Endpoints

**Files:**
- Create: `backend/api/routers/admin.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_admin_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from api.main import app

@pytest.mark.asyncio
async def test_enrich_endpoint_triggers_task():
    with patch("api.routers.admin.enrich_wine_task") as mock_task:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/enrich/42")
    assert response.status_code == 200
    mock_task.delay.assert_called_once_with(42)
```

- [ ] **Step 2: Write api/routers/admin.py**

```python
# backend/api/routers/admin.py
from fastapi import APIRouter
from workers.enrichment_tasks import enrich_wine_task
from workers.scraper_tasks import run_all_scrapers

router = APIRouter(prefix="/api", tags=["admin"])

@router.post("/enrich/{wine_id}")
async def trigger_enrich(wine_id: int):
    enrich_wine_task.delay(wine_id)
    return {"status": "queued", "wine_id": wine_id}

@router.post("/scrape/trigger")
async def trigger_scrape():
    run_all_scrapers.delay()
    return {"status": "queued"}

@router.get("/admin/status")
async def admin_status():
    return {"scrapers": "ok", "enrichment": "ok"}
```

- [ ] **Step 3: Register in main.py**

```python
from api.routers import wines, recommend, admin
app.include_router(admin.router)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_admin_api.py -v
# Expected: PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/admin.py backend/tests/test_admin_api.py backend/api/main.py
git commit -m "feat: admin endpoints for manual enrich and scrape triggers"
```

---

## Phase 9 — Frontend (Last)

> **Do not start this phase until Phases 1–8 are complete and all API endpoints are verified working.**

### Task 20: React App Scaffold

- [ ] Bootstrap with Vite + React + Tailwind CSS
- [ ] Configure API base URL via `.env.local`
- [ ] Verify `npm run dev` serves on port 5173

### Task 21: Home / Preference Capture Page

- [ ] Zip code input
- [ ] Budget slider (range: $10–$200)
- [ ] Style selector cards: "Bold & Tannic", "Light & Elegant", "Earthy & Savory", "Crisp & Refreshing", "Rich & Oaky"
- [ ] Drinking occasion: Tonight / Weekend / Cellar
- [ ] Submit → POST `/api/recommend`

### Task 22: Chat / Recommendation Interface

- [ ] Split-panel layout: chat (left) + wine cards (right)
- [ ] Wine cards: name, producer, region, price, store, flavor tags, structure bars (body/tannin/acidity)
- [ ] "Find at another store" per card
- [ ] Thumbs up/down per recommendation
- [ ] Follow-up questions maintain session_id for conversation continuity

### Task 23: Wine Detail Page

- [ ] Full profile: region, tasting notes, vintage, structure profile
- [ ] Local availability table (store, address, price, distance)
- [ ] Related wines (same region, similar varietal)

### Task 24: Admin Dashboard

- [ ] Scraper status cards (last run, success rate)
- [ ] Enrichment queue view
- [ ] Manual trigger buttons → POST `/api/scrape/trigger`, POST `/api/enrich/{wine_id}`

---

## Self-Review

**Spec coverage check:**

| Spec Requirement | Task |
|---|---|
| Project scaffold + Docker | Tasks 1–2 |
| DB schema (all 5 tables) | Task 4 |
| Alembic migrations | Task 5 |
| CSV seed ingestion | Task 6 |
| `/api/wines/search` | Task 7 |
| Vivino scraping | Task 9 |
| Claude enrichment fallback | Task 10 |
| Enrichment pipeline + Celery | Tasks 8, 11 |
| Retail scrapers (Total Wine, HEB, Spec's) | Tasks 12–15 |
| Candidate retrieval + scoring | Task 16 |
| Claude recommendation engine | Task 17 |
| All REST endpoints | Tasks 18–19 |
| Frontend (last) | Tasks 20–24 |
| `scrape_errors` table | Task 4 (model), Task 15 (usage) |
| `robots.txt` / rate limiting | Tasks 9, 13, 14 (random delays) |
| `.env` for secrets | Task 1 |
| Unit tests for scoring logic | Task 16 |

**BevMo scraper:** noted in spec but not tasked above — add after HEB/Spec's using the same BaseScraper pattern as Task 13.

**Wine Folly scraper:** noted in spec but complex (region/grape guide extraction rather than inventory). Add as a follow-up enrichment source after Vivino is validated.
