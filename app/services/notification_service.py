import logging
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.models.alert import Alert, AlertType
from app.services.alert_utils import alert_to_dict, confidence_for_alert
from app.services.realtime_dispatcher import realtime_dispatcher

logger = logging.getLogger(__name__)


class NotificationService:
    def create_alert_sync(
        self,
        session: Session,
        alert_type: AlertType,
        *,
        risky_device_id: Optional[int] = None,
        fire_event_id: Optional[int] = None,
        sensor_reading_id: Optional[int] = None,
        confidence: Optional[float] = None,
    ) -> Alert:
        alert = Alert(
            alert_type=alert_type,
            risky_device_id=risky_device_id,
            fire_event_id=fire_event_id,
            sensor_reading_id=sensor_reading_id,
        )
        session.add(alert)
        session.commit()
        session.refresh(alert)
        realtime_dispatcher.dispatch_alert_created(session, alert, confidence=confidence)
        logger.info("Created alert id=%s type=%s", alert.id, alert.alert_type)
        return alert

    async def create_alert(
        self,
        session: Session,
        alert_type: AlertType,
        risky_device_id: Optional[int] = None,
        fire_event_id: Optional[int] = None,
        sensor_reading_id: Optional[int] = None,
        confidence: Optional[float] = None,
    ) -> Alert:
        return self.create_alert_sync(
            session,
            alert_type,
            risky_device_id=risky_device_id,
            fire_event_id=fire_event_id,
            sensor_reading_id=sensor_reading_id,
            confidence=confidence,
        )

    async def notify_fire_detected(
        self,
        session: Session,
        fire_event_id: int,
        confidence: Optional[float] = None,
    ):
        await self.create_alert(
            session=session,
            alert_type=AlertType.FIRE_DETECTED,
            fire_event_id=fire_event_id,
            confidence=confidence,
        )

    async def acknowledge_alert(
        self,
        session: Session,
        alert_id: int,
        user_id: int,
    ) -> Optional[Alert]:
        return await self.resolve_alert(session, alert_id, user_id)

    async def resolve_alert(
        self,
        session: Session,
        alert_id: int,
        user_id: int,
    ) -> Optional[Alert]:
        statement = select(Alert).where(Alert.id == alert_id)
        alert = session.exec(statement).first()
        if not alert:
            return None
        if alert.resolved_at is None:
            alert.resolved_at = datetime.utcnow()
            session.add(alert)
            session.commit()
            session.refresh(alert)
            realtime_dispatcher.dispatch_alert_updated(session, alert)
        return alert


notification_service = NotificationService()
