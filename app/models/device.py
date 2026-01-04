from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from enum import Enum

if TYPE_CHECKING:
    from app.models.sensor import Sensor


class DeviceType(str, Enum):
    SENSOR = "sensor"
    CAMERA = "camera"
    ARM = "arm"
    RASPBERRY_PI = "raspberry_pi"


class DeviceStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class Device(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    device_type: DeviceType
    status: DeviceStatus = Field(default=DeviceStatus.OFFLINE)
    location: Optional[str] = None
    mqtt_topic: Optional[str] = None
    serial_port: Optional[str] = None
    ip_address: Optional[str] = None
    last_seen: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    sensors: List["Sensor"] = Relationship(back_populates="device")

