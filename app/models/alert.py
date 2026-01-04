from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, TYPE_CHECKING
from datetime import datetime
from enum import Enum

if TYPE_CHECKING:
    from app.models.user import User


class AlertType(str, Enum):
    FIRE_DETECTED = "fire_detected"
    HIGH_TEMPERATURE = "high_temperature"
    SMOKE_DETECTED = "smoke_detected"
    DEVICE_OFFLINE = "device_offline"
    SYSTEM_ERROR = "system_error"


class AlertStatus(str, Enum):
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    FALSE_ALARM = "false_alarm"


class Alert(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    alert_type: AlertType
    status: AlertStatus = Field(default=AlertStatus.PENDING)
    title: str
    message: str
    severity: int = Field(default=1, ge=1, le=5)  # 1-5 scale
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    sensor_id: Optional[int] = None
    device_id: Optional[int] = None
    fire_event_id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    
    # Relationships
    user: Optional["User"] = Relationship(back_populates="alerts")

