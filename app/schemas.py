from typing import Optional

from pydantic import BaseModel, Field


class Stop(BaseModel):
    name: str
    category: str
    indoor: bool
    lat: float
    lon: float
    arrive: str  # "HH:MM"
    leave: str  # "HH:MM"
    travel_minutes_from_prev: int
    weather_note: str
    reason: str
    source: str


class Itinerary(BaseModel):
    date: str  # "YYYY-MM-DD"
    stops: list[Stop] = Field(default_factory=list)


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    itinerary: Optional[Itinerary] = None
