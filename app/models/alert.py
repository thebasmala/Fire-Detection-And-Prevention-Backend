from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Enum as SAEnum
from typing import Optional
from datetime import datetime
from enum import Enum


class AlertType(str, Enum):
    FIRE_DETECTED = "fire_detected"
    RISKY_DEVICE_DETECTED = "risky_device_detected"
    HIGH_TEMP = "high_temp"
    GAS_DETECTED = "gas_detected"


class Alert(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    alert_type: AlertType = Field(
        sa_column=Column(
            SAEnum(
                AlertType,
                name="alerttype",
                values_callable=lambda enum_cls: [member.value for member in enum_cls],
            ),
            nullable=False,
        )
    )
    risky_device_id: Optional[int] = None
    fire_event_id: Optional[int] = None
    sensor_reading_id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None

