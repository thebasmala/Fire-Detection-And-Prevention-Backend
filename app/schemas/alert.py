from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.alert import AlertType, AlertStatus


class AlertBase(BaseModel):
    alert_type: AlertType
    title: str
    message: str
    severity: int = 1


class AlertCreate(AlertBase):
    sensor_id: Optional[int] = None
    device_id: Optional[int] = None
    fire_event_id: Optional[int] = None


class AlertUpdate(BaseModel):
    status: Optional[AlertStatus] = None
    title: Optional[str] = None
    message: Optional[str] = None
    severity: Optional[int] = None


class AlertRead(AlertBase):
    id: int
    status: AlertStatus
    user_id: Optional[int] = None
    sensor_id: Optional[int] = None
    device_id: Optional[int] = None
    fire_event_id: Optional[int] = None
    created_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

