from typing import List
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import settings
from app.database import get_session
from app.core.security import get_current_active_user, require_fire_frame_upload_auth
from app.core.storage import (
    FOLDER_DEVICE_FRAMES,
    FOLDER_FIRE_FRAMES,
    cloudinary_configured,
    save_image_bytes,
)
from app.models.user import User
from app.models.device import Device
from app.models.video_stream import VideoStream
from app.schemas.video_stream import VideoStreamCreate, VideoStreamRead
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video", tags=["Video"])


def _resolve_stream_or_404(session: Session, stream_id: int) -> VideoStream:
    stream = session.get(VideoStream, stream_id)
    if not stream:
        raise HTTPException(status_code=404, detail="Video stream not found")
    if not stream.is_active:
        raise HTTPException(status_code=400, detail="Video stream is not active")
    return stream


def _live_stream_response(stream: VideoStream) -> StreamingResponse:
    """Proxy MJPEG stream from the source camera URL."""
    async def generate():
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                async with client.stream("GET", stream.stream_url) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        yield chunk
            except httpx.RequestError as e:
                logger.error(f"Error streaming from {stream.stream_url}: {e}")
                yield b""
            except Exception as e:
                logger.error(f"Unexpected error in video stream: {e}")
                yield b""

    media_type = "multipart/x-mixed-replace; boundary=frame"
    if stream.stream_url.endswith(".mp4") or "mp4" in stream.stream_url:
        media_type = "video/mp4"
    elif "rtsp" in stream.stream_url.lower():
        media_type = "application/x-rtsp"

    return StreamingResponse(
        generate(),
        media_type=media_type,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",
        },
    )


class FireFrameUploadResponse(BaseModel):
    url: str
    filename: str


@router.post(
    "/fire-frames/upload",
    response_model=FireFrameUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_fire_frame(
    request: Request,
    file: UploadFile = File(...),
    _: None = Depends(require_fire_frame_upload_auth),
):
    """Store a fire snapshot and return a public URL for MQTT / DB."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    base = (settings.public_api_base_url or str(request.base_url)).rstrip("/")
    try:
        public_url, stored_name = save_image_bytes(
            data,
            FOLDER_FIRE_FRAMES,
            original_filename=file.filename or "frame.jpg",
            public_base_url=base,
        )
    except Exception as exc:
        logger.exception("Fire frame upload failed")
        raise HTTPException(status_code=500, detail="Failed to store fire frame") from exc
    logger.info(
        "Fire frame upload OK (cloudinary=%s): %s",
        cloudinary_configured(),
        public_url,
    )
    return FireFrameUploadResponse(url=public_url, filename=stored_name)


@router.post(
    "/frames/upload",
    response_model=FireFrameUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_general_frame(
    request: Request,
    file: UploadFile = File(...),
    _: None = Depends(require_fire_frame_upload_auth),
):
    """Store risky-device snapshot and return public URL."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    base = (settings.public_api_base_url or str(request.base_url)).rstrip("/")
    try:
        public_url, stored_name = save_image_bytes(
            data,
            FOLDER_DEVICE_FRAMES,
            original_filename=file.filename or "frame.jpg",
            public_base_url=base,
        )
    except Exception as exc:
        logger.exception("Device frame upload failed")
        raise HTTPException(status_code=500, detail="Failed to store device frame") from exc
    logger.info(
        "Device frame upload OK (cloudinary=%s): %s",
        cloudinary_configured(),
        public_url,
    )
    return FireFrameUploadResponse(url=public_url, filename=stored_name)


@router.post("/streams", response_model=VideoStreamRead, status_code=status.HTTP_201_CREATED)
async def create_video_stream(
    stream_data: VideoStreamCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new video stream"""
    if session.get(Device, stream_data.device_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device id={stream_data.device_id} does not exist. Create a device first (POST /api/devices) or use GET /api/devices for valid ids.",
        )
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
    current_user: User = Depends(get_current_active_user),
):
    """Stream live video from Raspberry Pi camera"""
    stream = _resolve_stream_or_404(session, stream_id)
    return _live_stream_response(stream)


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
