from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class FireEventBase(BaseModel):
    zone: Optional[int] = None
    confidence: Optional[float] = None
    frame: Optional[str] = None


class FireEventCreate(FireEventBase):
    detected_at: Optional[datetime] = None


class FireEventUpdate(BaseModel):
    zone: Optional[int] = None
    confidence: Optional[float] = None
    frame: Optional[str] = None
    resolved_at: Optional[datetime] = None


class FireEventRead(FireEventBase):
    id: int
    detected_at: datetime
    resolved_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

