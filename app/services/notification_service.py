import logging
from typing import List, Optional
from sqlmodel import Session, select
from datetime import datetime
from app.models.alert import Alert, AlertType, AlertStatus
from app.models.user import User
from app.core.mqtt_client import mqtt_client

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self):
        self.mqtt_client = mqtt_client
    
    async def create_alert(
        self,
        session: Session,
        alert_type: AlertType,
        title: str,
        message: str,
        severity: int = 1,
        sensor_id: Optional[int] = None,
        device_id: Optional[int] = None,
        fire_event_id: Optional[int] = None
    ) -> Alert:
        """Create a new alert and notify users"""
        alert = Alert(
            alert_type=alert_type,
            title=title,
            message=message,
            severity=severity,
            sensor_id=sensor_id,
            device_id=device_id,
            fire_event_id=fire_event_id
        )
        session.add(alert)
        session.commit()
        session.refresh(alert)
        
        # Send notification via MQTT
        self._send_mqtt_notification(alert)
        
        logger.info(f"Created alert: {alert.id} - {title}")
        return alert
    
    def _send_mqtt_notification(self, alert: Alert):
        """Send alert notification via MQTT"""
        notification = {
            "alert_id": alert.id,
            "type": alert.alert_type,
            "title": alert.title,
            "message": alert.message,
            "severity": alert.severity,
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
        title = "Fire Detected!"
        message = f"Fire detected at {location}" if location else "Fire detected in the system"
        
        await self.create_alert(
            session=session,
            alert_type=AlertType.FIRE_DETECTED,
            title=title,
            message=message,
            severity=5,
            fire_event_id=fire_event_id
        )
    
    async def notify_device_offline(
        self,
        session: Session,
        device_id: int,
        device_name: str
    ):
        """Create and send device offline alert"""
        await self.create_alert(
            session=session,
            alert_type=AlertType.DEVICE_OFFLINE,
            title=f"Device Offline: {device_name}",
            message=f"Device {device_name} is offline and not responding",
            severity=2,
            device_id=device_id
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
        
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.user_id = user_id
        alert.acknowledged_at = datetime.utcnow()
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
        
        alert.status = AlertStatus.RESOLVED
        alert.user_id = user_id
        alert.resolved_at = datetime.utcnow()
        session.add(alert)
        session.commit()
        session.refresh(alert)
        
        return alert


notification_service = NotificationService()

