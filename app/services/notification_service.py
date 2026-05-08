import logging
from typing import Optional
from sqlmodel import Session, select
from datetime import datetime
from app.models.alert import Alert, AlertType
from app.core.mqtt_client import mqtt_client

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self):
        self.mqtt_client = mqtt_client
    
    async def create_alert(
        self,
        session: Session,
        alert_type: AlertType,
        risky_device_id: Optional[int] = None,
        fire_event_id: Optional[int] = None,
        sensor_reading_id: Optional[int] = None,
    ) -> Alert:
        """Create a new reference-based alert and notify users"""
        alert = Alert(
            alert_type=alert_type,
            risky_device_id=risky_device_id,
            fire_event_id=fire_event_id,
            sensor_reading_id=sensor_reading_id,
        )
        session.add(alert)
        session.commit()
        session.refresh(alert)
        
        # Send notification via MQTT
        self._send_mqtt_notification(alert)
        
        logger.info(f"Created alert: {alert.id} - {alert.alert_type}")
        return alert
    
    def _send_mqtt_notification(self, alert: Alert):
        """Send alert notification via MQTT"""
        notification = {
            "alert_id": alert.id,
            "type": alert.alert_type,
            "risky_device_id": alert.risky_device_id,
            "fire_event_id": alert.fire_event_id,
            "sensor_reading_id": alert.sensor_reading_id,
            "timestamp": alert.created_at.isoformat()
        }
        self.mqtt_client.publish("notifications/alerts", notification)
    
    async def notify_fire_detected(
        self,
        session: Session,
        fire_event_id: int,
        location: Optional[str] = None
    ):
        """Create and send fire detection alert"""
        await self.create_alert(
            session=session,
            alert_type=AlertType.FIRE_DETECTED,
            fire_event_id=fire_event_id
        )
    
    async def notify_device_offline(
        self,
        session: Session,
        device_id: int,
        device_name: str
    ):
        """Create and send gas/system availability alert"""
        await self.create_alert(
            session=session,
            alert_type=AlertType.GAS_DETECTED
        )
    
    async def acknowledge_alert(
        self,
        session: Session,
        alert_id: int,
        user_id: int
    ) -> Optional[Alert]:
        """Acknowledge an alert"""
        statement = select(Alert).where(Alert.id == alert_id)
        alert = session.exec(statement).first()
        
        if not alert:
            return None
        
        # With slim alert model, acknowledge and resolve share resolved_at.
        alert.resolved_at = datetime.utcnow()
        session.add(alert)
        session.commit()
        session.refresh(alert)
        
        return alert
    
    async def resolve_alert(
        self,
        session: Session,
        alert_id: int,
        user_id: int
    ) -> Optional[Alert]:
        """Resolve an alert"""
        statement = select(Alert).where(Alert.id == alert_id)
        alert = session.exec(statement).first()
        
        if not alert:
            return None
        
        alert.resolved_at = datetime.utcnow()
        session.add(alert)
        session.commit()
        session.refresh(alert)
        
        return alert


notification_service = NotificationService()

