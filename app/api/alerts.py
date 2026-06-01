from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.database import get_session
from app.core.security import get_current_active_user
from app.models.user import User
from app.models.alert import Alert, AlertType
from app.schemas.alert import AlertCreate, AlertRead, AlertUpdate
from app.services.alert_utils import frame_url_for_alert, zone_for_alert
from app.services.notification_service import notification_service
from app.services.realtime_dispatcher import realtime_dispatcher

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def _to_read(session: Session, alert: Alert) -> AlertRead:
    return AlertRead(
        id=alert.id,
        alert_type=alert.alert_type,
        risky_device_id=alert.risky_device_id,
        fire_event_id=alert.fire_event_id,
        sensor_reading_id=alert.sensor_reading_id,
        created_at=alert.created_at,
        resolved_at=alert.resolved_at,
        frame_url=frame_url_for_alert(session, alert),
        zone=zone_for_alert(session, alert),
    )


@router.get("", response_model=List[AlertRead])
async def get_alerts(
    skip: int = 0,
    limit: int = Query(100, le=500),
    alert_type: Optional[AlertType] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    statement = select(Alert)
    if alert_type is not None:
        statement = statement.where(Alert.alert_type == alert_type)
    statement = statement.order_by(Alert.created_at.desc()).offset(skip).limit(limit)
    alerts = session.exec(statement).all()
    return [_to_read(session, a) for a in alerts]


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(
    alert_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _to_read(session, alert)


@router.post("", response_model=AlertRead, status_code=status.HTTP_201_CREATED)
async def create_alert(
    alert_data: AlertCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    alert = await notification_service.create_alert(
        session=session,
        alert_type=alert_data.alert_type,
        risky_device_id=alert_data.risky_device_id,
        fire_event_id=alert_data.fire_event_id,
        sensor_reading_id=alert_data.sensor_reading_id,
    )
    return _to_read(session, alert)


@router.patch("/{alert_id}", response_model=AlertRead)
async def update_alert(
    alert_id: int,
    alert_data: AlertUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    update_data = alert_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(alert, field, value)

    session.add(alert)
    session.commit()
    session.refresh(alert)
    realtime_dispatcher.dispatch_alert_updated(session, alert)
    return _to_read(session, alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertRead)
async def acknowledge_alert(
    alert_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    alert = await notification_service.acknowledge_alert(
        session=session,
        alert_id=alert_id,
        user_id=current_user.id,
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _to_read(session, alert)


@router.post("/{alert_id}/resolve", response_model=AlertRead)
async def resolve_alert(
    alert_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    alert = await notification_service.resolve_alert(
        session=session,
        alert_id=alert_id,
        user_id=current_user.id,
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _to_read(session, alert)
