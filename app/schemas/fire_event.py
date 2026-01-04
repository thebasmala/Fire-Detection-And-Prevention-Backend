from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.fire_event import FireEventStatus


class FireEventBase(BaseModel):
    location: Optional[str] = None
    angle: Optional[float] = None
    x_coordinate: Optional[float] = None
    y_coordinate: Optional[float] = None
    confidence: Optional[float] = None
    temperature: Optional[float] = None


class FireEventCreate(FireEventBase):
    device_id: Optional[int] = None
    camera_id: Optional[int] = None
    video_url: Optional[str] = None


class FireEventUpdate(BaseModel):
    status: Optional[FireEventStatus] = None
    location: Optional[str] = None
    angle: Optional[float] = None
    x_coordinate: Optional[float] = None
    y_coordinate: Optional[float] = None
    confidence: Optional[float] = None
    temperature: Optional[float] = None
    video_url: Optional[str] = None


class FireEventRead(FireEventBase):
    id: int
    status: FireEventStatus
    device_id: Optional[int] = None
    camera_id: Optional[int] = None
    video_url: Optional[str] = None
    detected_at: datetime
    confirmed_at: Optional[datetime] = None
    suppressed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

