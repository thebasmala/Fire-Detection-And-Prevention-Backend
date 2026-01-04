from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.sensor import SensorType


class SensorBase(BaseModel):
    name: str
    sensor_type: SensorType
    threshold: Optional[float] = None
    unit: Optional[str] = None
    is_active: bool = True


class SensorCreate(SensorBase):
    device_id: int


class SensorUpdate(BaseModel):
    name: Optional[str] = None
    sensor_type: Optional[SensorType] = None
    threshold: Optional[float] = None
    unit: Optional[str] = None
    is_active: Optional[bool] = None


class SensorRead(SensorBase):
    id: int
    device_id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class SensorReadingCreate(BaseModel):
    sensor_id: int
    value: float


class SensorReadingRead(BaseModel):
    id: int
    sensor_id: int
    value: float
    timestamp: datetime
    
    class Config:
        from_attributes = True

