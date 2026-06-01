from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.alert import AlertType


class AlertBase(BaseModel):
    alert_type: AlertType


class AlertCreate(AlertBase):
    risky_device_id: Optional[int] = None
    fire_event_id: Optional[int] = None
    sensor_reading_id: Optional[int] = None


class AlertUpdate(BaseModel):
    resolved_at: Optional[datetime] = None


class AlertRead(AlertBase):
    id: int
    risky_device_id: Optional[int] = None
    fire_event_id: Optional[int] = None
    sensor_reading_id: Optional[int] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
    frame_url: Optional[str] = None
    zone: Optional[int] = None

    class Config:
        from_attributes = True
