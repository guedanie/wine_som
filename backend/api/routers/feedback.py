from fastapi import APIRouter
from api.schemas import FeedbackRequest
from db import get_service_client

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("", status_code=200)
async def post_feedback(body: FeedbackRequest):
    client = get_service_client()
    client.table("feedback").upsert(
        {
            "type":       body.type,
            "entity_id":  body.entity_id,
            "vote":       body.vote,
            "session_id": body.session_id,
            "user_id":    body.user_id,
            "zip":        body.zip,
        },
        on_conflict="session_id,entity_id,type",
    ).execute()
    return {"ok": True}
