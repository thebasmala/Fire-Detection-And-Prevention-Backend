from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class VideoStream(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="device.id")
    stream_url: str
    is_active: bool = Field(default=True)
    resolution: Optional[str] = None
    fps: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

