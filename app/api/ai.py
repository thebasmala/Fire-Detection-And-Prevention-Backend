from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlmodel import Session
from app.database import get_session
from app.core.security import get_current_active_user
from app.models.user import User
from app.services.ai_service import ai_service
from typing import Dict, Any

router = APIRouter(prefix="/ai", tags=["AI Models"])


@router.post("/detect-risk")
async def detect_high_risk_devices(
    device_data: Dict[str, Any],
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Call AI model to detect high-risk devices"""
    result = await ai_service.detect_high_risk_devices(device_data)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service unavailable"
        )
    return result


@router.post("/locate-fire")
async def locate_fire(
    image: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Call AI model to locate fire angle and position"""
    image_data = await image.read()
    result = await ai_service.locate_fire(image_data)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service unavailable"
        )
    return result

