from typing import List
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from app.database import get_session
from app.core.security import get_current_active_user
from app.models.user import User
from app.models.video_stream import VideoStream
from app.schemas.video_stream import VideoStreamCreate, VideoStreamRead
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video", tags=["Video"])


@router.post("/streams", response_model=VideoStreamRead, status_code=status.HTTP_201_CREATED)
async def create_video_stream(
    stream_data: VideoStreamCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new video stream"""
    stream = VideoStream(**stream_data.model_dump())
    session.add(stream)
    session.commit()
    session.refresh(stream)
    return stream


@router.get("/streams", response_model=List[VideoStreamRead])
async def get_video_streams(
    device_id: int = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get all video streams, optionally filtered by device"""
    if device_id:
        statement = select(VideoStream).where(VideoStream.device_id == device_id)
    else:
        statement = select(VideoStream)
    streams = session.exec(statement).all()
    return streams


@router.get("/streams/{stream_id}", response_model=VideoStreamRead)
async def get_video_stream(
    stream_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific video stream"""
    stream = session.get(VideoStream, stream_id)
    if not stream:
        raise HTTPException(status_code=404, detail="Video stream not found")
    return stream


@router.get("/streams/{stream_id}/live")
async def stream_live_video(
    stream_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Stream live video from Raspberry Pi camera"""
    stream = session.get(VideoStream, stream_id)
    if not stream:
        raise HTTPException(status_code=404, detail="Video stream not found")
    
    if not stream.is_active:
        raise HTTPException(status_code=400, detail="Video stream is not active")
    
    # Proxy the video stream from Raspberry Pi
    # Supports MJPEG streams (multipart/x-mixed-replace)
    async def generate():
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                async with client.stream("GET", stream.stream_url) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        yield chunk
            except httpx.RequestError as e:
                logger.error(f"Error streaming from {stream.stream_url}: {e}")
                # Return error frame or empty
                yield b''
            except Exception as e:
                logger.error(f"Unexpected error in video stream: {e}")
                yield b''
    
    # Determine media type based on stream URL
    # MJPEG streams use multipart/x-mixed-replace
    media_type = "multipart/x-mixed-replace; boundary=frame"
    if stream.stream_url.endswith('.mp4') or 'mp4' in stream.stream_url:
        media_type = "video/mp4"
    elif 'rtsp' in stream.stream_url.lower():
        media_type = "application/x-rtsp"
    
    return StreamingResponse(
        generate(),
        media_type=media_type,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no"
        }
    )


@router.delete("/streams/{stream_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video_stream(
    stream_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a video stream"""
    stream = session.get(VideoStream, stream_id)
    if not stream:
        raise HTTPException(status_code=404, detail="Video stream not found")
    
    session.delete(stream)
    session.commit()
    return None

