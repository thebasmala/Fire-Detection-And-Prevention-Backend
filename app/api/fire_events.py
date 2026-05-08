from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from app.database import get_session
from app.core.security import get_current_active_user
from app.models.user import User
from app.models.fire_event import FireEvent
from app.schemas.fire_event import FireEventCreate, FireEventRead, FireEventUpdate
from app.services.notification_service import notification_service
from app.services.ai_service import ai_service
from datetime import datetime

router = APIRouter(prefix="/fire-events", tags=["Fire Events"])


@router.get("", response_model=List[FireEventRead])
async def get_fire_events(
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get all fire events"""
    statement = select(FireEvent).offset(skip).limit(limit)
    statement = statement.order_by(FireEvent.detected_at.desc())
    events = session.exec(statement).all()
    return events


@router.get("/{event_id}", response_model=FireEventRead)
async def get_fire_event(
    event_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific fire event"""
    event = session.get(FireEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Fire event not found")
    return event


@router.post("", response_model=FireEventRead, status_code=status.HTTP_201_CREATED)
async def create_fire_event(
    event_data: FireEventCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new fire event"""
    event_payload = event_data.model_dump(exclude_unset=True)
    if event_payload.get("detected_at") is None:
        event_payload["detected_at"] = datetime.utcnow()
    event = FireEvent(**event_payload)
    session.add(event)
    session.commit()
    session.refresh(event)
    
    # Send notification
    await notification_service.notify_fire_detected(
        session=session,
        fire_event_id=event.id,
        location=None,
    )
    
    return event


@router.patch("/{event_id}", response_model=FireEventRead)
async def update_fire_event(
    event_id: int,
    event_data: FireEventUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Update a fire event"""
    event = session.get(FireEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Fire event not found")
    
    update_data = event_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(event, field, value)

    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.post("/{event_id}/locate-fire", response_model=FireEventRead)
async def locate_fire(
    event_id: int,
    image_data: bytes,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Use AI model to locate fire position and update event"""
    event = session.get(FireEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Fire event not found")
    
    # Call AI service to locate fire
    result = await ai_service.locate_fire(image_data)
    
    if result:
        event.confidence = result.get("confidence")
        session.add(event)
        session.commit()
        session.refresh(event)
    
    return event


@router.post("/{event_id}/suppress", response_model=FireEventRead)
async def suppress_fire(
    event_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Mark fire event as resolved"""
    event = session.get(FireEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Fire event not found")
    
    event.resolved_at = datetime.utcnow()
    session.add(event)
    session.commit()
    session.refresh(event)

    return event

