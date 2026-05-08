from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from app.database import get_session
from app.core.security import get_current_active_user
from app.models.user import User
from app.models.alert import Alert
from app.schemas.alert import AlertCreate, AlertRead, AlertUpdate
from app.services.notification_service import notification_service

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("", response_model=List[AlertRead])
async def get_alerts(
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get all alerts"""
    statement = select(Alert).offset(skip).limit(limit)
    statement = statement.order_by(Alert.created_at.desc())
    alerts = session.exec(statement).all()
    return alerts


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(
    alert_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific alert"""
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("", response_model=AlertRead, status_code=status.HTTP_201_CREATED)
async def create_alert(
    alert_data: AlertCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new alert"""
    alert = await notification_service.create_alert(
        session=session,
        alert_type=alert_data.alert_type,
        risky_device_id=alert_data.risky_device_id,
        fire_event_id=alert_data.fire_event_id,
        sensor_reading_id=alert_data.sensor_reading_id,
    )
    return alert


@router.patch("/{alert_id}", response_model=AlertRead)
async def update_alert(
    alert_id: int,
    alert_data: AlertUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Update an alert"""
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    update_data = alert_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(alert, field, value)
    
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


@router.post("/{alert_id}/acknowledge", response_model=AlertRead)
async def acknowledge_alert(
    alert_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Acknowledge an alert"""
    alert = await notification_service.acknowledge_alert(
        session=session,
        alert_id=alert_id,
        user_id=current_user.id
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/{alert_id}/resolve", response_model=AlertRead)
async def resolve_alert(
    alert_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Resolve an alert"""
    alert = await notification_service.resolve_alert(
        session=session,
        alert_id=alert_id,
        user_id=current_user.id
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert

