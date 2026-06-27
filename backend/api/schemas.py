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


class RegionWineItem(BaseModel):
    wine_id: str
    name: str
    varietal: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    wine_type: Optional[str] = None
    price: float
    retailer: str
    store_address: Optional[str] = None
    image_url: Optional[str] = None
    flavor_profile: List[str] = []
    grapes: List[str] = []


class RegionRetailerGroup(BaseModel):
    retailer: str
    wines: List[RegionWineItem]


class RegionResponse(BaseModel):
    region: str
    retailers: List[RegionRetailerGroup]


class RecommendRequest(BaseModel):
    zip_code: str
    budget_min: float = 10.0
    budget_max: float = 50.0
    style_preferences: List[str] = []
    avoid: List[str] = []
    wine_type: Optional[str] = None          # legacy single-type (kept for compat)
    wine_types: List[str] = []               # multi-select; takes precedence over wine_type
    grapes: List[str] = []                   # explicit varietal filter from advanced search
    message: str = "Recommend wines based on my preferences"
    conversation_history: Optional[List[Dict[str, Any]]] = None


class WinePick(BaseModel):
    wine_id: str
    name: str
    price: float
    retailer: str
    why: str
    store_address: Optional[str] = None


class RecommendResponse(BaseModel):
    narrative: str
    picks: List[WinePick]
    session_id: str
