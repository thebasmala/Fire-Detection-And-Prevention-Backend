from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class VideoStreamBase(BaseModel):
    stream_url: str
    resolution: Optional[str] = None
    fps: Optional[int] = None
    is_active: bool = True


class VideoStreamCreate(VideoStreamBase):
    device_id: int


class VideoStreamRead(VideoStreamBase):
    id: int
    device_id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

