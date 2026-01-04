from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from app.database import get_session
from app.core.security import get_current_active_user
from app.models.user import User
from app.models.fire_event import FireEvent, FireEventStatus
from app.schemas.fire_event import FireEventCreate, FireEventRead, FireEventUpdate
from app.services.notification_service import notification_service
from app.services.ai_service import ai_service
from app.core.serial_client import serial_client
from datetime import datetime

router = APIRouter(prefix="/fire-events", tags=["Fire Events"])


@router.get("", response_model=List[FireEventRead])
async def get_fire_events(
    status_filter: Optional[FireEventStatus] = None,
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get all fire events, optionally filtered by status"""
    if status_filter:
        statement = select(FireEvent).where(FireEvent.status == status_filter).offset(skip).limit(limit)
    else:
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
    event = FireEvent(**event_data.model_dump())
    session.add(event)
    session.commit()
    session.refresh(event)
    
    # Send notification
    await notification_service.notify_fire_detected(
        session=session,
        fire_event_id=event.id,
        location=event.location
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
    
    event.updated_at = datetime.utcnow()
    
    # If status changed to confirmed, update confirmed_at
    if event_data.status == FireEventStatus.CONFIRMED and not event.confirmed_at:
        event.confirmed_at = datetime.utcnow()
    
    # If status changed to suppressed, update suppressed_at and activate arm
    if event_data.status == FireEventStatus.SUPPRESSING:
        if event.angle and event.x_coordinate and event.y_coordinate:
            serial_client.move_arm(event.angle, event.x_coordinate, event.y_coordinate)
        serial_client.activate_arm()
        event.suppressed_at = datetime.utcnow()
    
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
        event.angle = result.get("angle")
        event.x_coordinate = result.get("x")
        event.y_coordinate = result.get("y")
        event.confidence = result.get("confidence")
        event.updated_at = datetime.utcnow()
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
    """Activate fire suppression arm for a fire event"""
    event = session.get(FireEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Fire event not found")
    
    if event.angle and event.x_coordinate and event.y_coordinate:
        # Move arm to fire location
        serial_client.move_arm(event.angle, event.x_coordinate, event.y_coordinate)
    
    # Activate arm
    success = serial_client.activate_arm()
    
    if success:
        event.status = FireEventStatus.SUPPRESSING
        event.suppressed_at = datetime.utcnow()
        event.updated_at = datetime.utcnow()
        session.add(event)
        session.commit()
        session.refresh(event)
    
    return event

