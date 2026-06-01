"""WebSocket broadcast: alerts (with frame URLs) and live sensor readings."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from sqlmodel import Session

from app.config import settings
from app.core.ws_manager import ws_manager
from app.models.alert import Alert
from app.services.alert_utils import (
    alert_to_ws_payload,
    confidence_for_alert,
    format_confidence,
    zone_for_alert,
)
from app.services.outbound_notify import notify_high_confidence_users

logger = logging.getLogger(__name__)


def _should_popup(confidence: Optional[float]) -> bool:
    if confidence is None:
        return False
    c, _ = format_confidence(confidence)
    if c is None:
        return False
    return c >= settings.high_confidence_threshold


def _confidence_fields(confidence: Optional[float]) -> Dict[str, Any]:
    c, percent = format_confidence(confidence)
    return {
        "confidence": c,
        "confidence_percent": percent,
    }


class RealtimeDispatcher:
    def _broadcast(self, message: dict) -> None:
        ws_manager.schedule_broadcast(message)

    def dispatch_alert_created(
        self,
        session: Session,
        alert: Alert,
        *,
        confidence: Optional[float] = None,
    ) -> None:
        if confidence is None:
            confidence = confidence_for_alert(session, alert)
        popup = _should_popup(confidence)
        zone = zone_for_alert(session, alert)
        self._broadcast(
            {
                "event": "alert_created",
                "popup": popup,
                "zone": zone,
                **_confidence_fields(confidence),
                "data": alert_to_ws_payload(session, alert),
            }
        )
        if popup and confidence is not None:
            _, percent = format_confidence(confidence)
            logger.info(
                "High-confidence alert id=%s zone=%s (%s%%) — scheduling email/SMS/FCM",
                alert.id,
                zone,
                percent,
            )
            self._schedule_outbound(alert.id, confidence)

    def dispatch_alert_updated(self, session: Session, alert: Alert) -> None:
        conf = confidence_for_alert(session, alert)
        self._broadcast(
            {
                "event": "alert_updated",
                "popup": False,
                "zone": zone_for_alert(session, alert),
                **_confidence_fields(conf),
                "data": alert_to_ws_payload(session, alert),
            }
        )

    def dispatch_sensor_reading(
        self,
        *,
        sensor_id: int,
        value: float,
        status: str,
        device_id: Optional[int] = None,
        sensor_name: Optional[str] = None,
        unit: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        self._broadcast(
            {
                "event": "sensor_reading",
                "popup": False,
                "confidence": None,
                "confidence_percent": None,
                "data": {
                    "sensor_id": sensor_id,
                    "sensor_name": sensor_name,
                    "value": round(float(value), 2),
                    "status": status,
                    "unit": unit,
                    "device_id": device_id,
                    "timestamp": timestamp,
                },
            }
        )

    def _schedule_outbound(self, alert_id: int, confidence: float) -> None:
        loop = ws_manager._loop
        if loop is None or not loop.is_running():
            logger.warning("Cannot schedule email/SMS: event loop not running")
            return
        try:
            asyncio.run_coroutine_threadsafe(
                notify_high_confidence_users(alert_id=alert_id, confidence=confidence),
                loop,
            )
        except Exception as exc:
            logger.warning("Could not schedule email/SMS notify: %s", exc)


realtime_dispatcher = RealtimeDispatcher()
