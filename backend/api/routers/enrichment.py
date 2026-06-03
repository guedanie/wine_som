from fastapi import APIRouter, BackgroundTasks, HTTPException
from db import get_service_client
from enrichment.pipeline import enrich_wine_with_refetch, enrich_batch

router = APIRouter(prefix="/api", tags=["enrichment"])


@router.post("/enrich/{wine_id}", status_code=202)
async def enrich_single(wine_id: str, background_tasks: BackgroundTasks, force: bool = False):
    """
    Trigger enrichment for a single wine. Runs in the background.
    - force=true re-enriches even if already cached
    - Returns immediately; enrichment (including refetch delay) happens async
    """
    client = get_service_client()
    result = (
        client.table("wines")
        .select("id,name,varietal,region")
        .eq("id", wine_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Wine {wine_id} not found")

    wine_row = result.data
    background_tasks.add_task(enrich_wine_with_refetch, wine_row)
    return {"status": "queued", "wine_id": wine_id, "wine_name": wine_row.get("name")}


@router.post("/enrich/batch/pending", status_code=202)
async def enrich_pending(background_tasks: BackgroundTasks, limit: int = 20):
    """
    Queue enrichment for wines that have no wine_details record yet.
    Processes up to `limit` wines (default 20, max 50) to stay within GrapeMinds budget.
    """
    if limit > 50:
        limit = 50

    client = get_service_client()

    # Find wines with no wine_details row at all
    enriched_ids_result = (
        client.table("wine_details")
        .select("wine_id")
        .not_.is_("grapeminds_enriched_at", "null")
        .execute()
    )
    enriched_ids = {r["wine_id"] for r in (enriched_ids_result.data or [])}

    all_wines = client.table("wines").select("id,name,varietal,region").limit(200).execute()
    pending = [w for w in (all_wines.data or []) if w["id"] not in enriched_ids][:limit]

    if not pending:
        return {"status": "nothing_to_enrich", "queued": 0}

    background_tasks.add_task(enrich_batch, pending)
    return {
        "status": "queued",
        "queued": len(pending),
        "wine_names": [w["name"] for w in pending[:5]],
    }
