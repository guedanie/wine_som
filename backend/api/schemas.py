from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class WineSearchResult(BaseModel):
    id: str
    name: str
    brand: Optional[str] = None
    varietal: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    avg_price: Optional[float] = None
    wine_type: Optional[str] = None


class RecommendRequest(BaseModel):
    zip_code: str
    budget_min: float = 10.0
    budget_max: float = 50.0
    style_preferences: List[str] = []
    avoid: List[str] = []
    wine_type: Optional[str] = None
    message: str = "Recommend wines based on my preferences"
    conversation_history: Optional[List[Dict[str, Any]]] = None


class WinePick(BaseModel):
    wine_id: str
    name: str
    price: float
    retailer: str
    why: str


class RecommendResponse(BaseModel):
    narrative: str
    picks: List[WinePick]
    session_id: str
