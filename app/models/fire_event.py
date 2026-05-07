from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class FireEventStatus(str, Enum):
    DETECTED = "detected"
    CONFIRMED = "confirmed"
    SUPPRESSING = "suppressing"
    SUPPRESSED = "suppressed"
    FALSE_ALARM = "false_alarm"


class FireEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    status: FireEventStatus = Field(default=FireEventStatus.DETECTED)
    # Turret zone (1-4). Kept optional because older payloads may not include it yet.
    zone: Optional[int] = None
    confidence: Optional[float] = None  # AI model confidence (0-1)
    temperature: Optional[float] = None
    device_id: Optional[int] = None
    camera_id: Optional[int] = None
    video_url: Optional[str] = None
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    confirmed_at: Optional[datetime] = None
    suppressed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

