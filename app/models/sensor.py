from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from enum import Enum

if TYPE_CHECKING:
    from app.models.device import Device


class SensorType(str, Enum):
    TEMPERATURE = "temperature"
    SMOKE = "smoke"
    FLAME = "flame"
    GAS = "gas"
    HUMIDITY = "humidity"


class SensorStatus(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


class Sensor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    sensor_type: SensorType
    device_id: int = Field(foreign_key="device.id")
    threshold: Optional[float] = None
    unit: Optional[str] = None
    is_active: bool = Field(default=True)
    # Live status fields for UI (avoid PostgreSQL reserved name "last_value")
    current_value: Optional[float] = None
    current_reading_at: Optional[datetime] = None
    status: SensorStatus = Field(default=SensorStatus.NORMAL)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    device: "Device" = Relationship(back_populates="sensors")
    readings: List["SensorReading"] = Relationship(back_populates="sensor")


class SensorReading(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sensor_id: int = Field(foreign_key="sensor.id")
    value: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    sensor: "Sensor" = Relationship(back_populates="readings")

