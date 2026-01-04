from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.device import DeviceType, DeviceStatus


class DeviceBase(BaseModel):
    name: str
    device_type: DeviceType
    location: Optional[str] = None
    mqtt_topic: Optional[str] = None
    serial_port: Optional[str] = None
    ip_address: Optional[str] = None


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    device_type: Optional[DeviceType] = None
    status: Optional[DeviceStatus] = None
    location: Optional[str] = None
    mqtt_topic: Optional[str] = None
    serial_port: Optional[str] = None
    ip_address: Optional[str] = None


class DeviceRead(DeviceBase):
    id: int
    status: DeviceStatus
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

