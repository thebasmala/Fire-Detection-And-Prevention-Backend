from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class RiskyDevice(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_type: str
    confidence: float
    zone: Optional[int] = None
    frame: Optional[str] = None
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
