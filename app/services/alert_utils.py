"""Alert helpers: serialization, confidence, zone, frame URLs, notification copy."""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlmodel import Session

from app.models.alert import Alert, AlertType
from app.models.fire_event import FireEvent
from app.models.risky_device import RiskyDevice

logger = logging.getLogger(__name__)

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def alert_type_value(alert_type: AlertType | str) -> str:
    if isinstance(alert_type, AlertType):
        return alert_type.value
    return str(alert_type)


def is_public_http_url(value: Optional[str]) -> bool:
    if not value:
        return False
    v = str(value).strip().lower()
    return v.startswith("http://") or v.startswith("https://")


def public_frame_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = str(value).strip()
    if is_public_http_url(cleaned):
        return cleaned
    return None


def resolve_public_frame_from_mqtt(payload: dict) -> Optional[str]:
    url = public_frame_url(payload.get("frame_url"))
    if url:
        return url
    local_path = (
        payload.get("frame_path")
        or payload.get("fire_frame_path")
        or payload.get("fire_frame")
        or payload.get("image_path")
    )
    if local_path:
        logger.warning(
            "MQTT has no public frame_url (Pi → POST /api/video/.../upload likely failed). "
            "Not saving local path: %s",
            local_path,
        )
    return None


def normalize_phone_number(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip().replace(" ", "").replace("-", "")
    if not cleaned:
        return None
    if not cleaned.startswith("+"):
        cleaned = f"+{cleaned.lstrip('+')}"
    return cleaned


def validate_phone_e164(value: Optional[str]) -> Optional[str]:
    normalized = normalize_phone_number(value)
    if normalized is None:
        return None
    if not _E164_RE.match(normalized):
        raise ValueError(
            "phone_number must be E.164 format, e.g. +201234567890 (no spaces)"
        )
    return normalized


def format_confidence(confidence: Optional[float]) -> Tuple[Optional[float], Optional[int]]:
    if confidence is None:
        return None, None
    c = round(float(confidence), 2)
    if c > 1.0 and c <= 100.0:
        c = round(c / 100.0, 2)
    percent = int(round(c * 100))
    return c, percent


def zone_for_alert(session: Session, alert: Alert) -> Optional[int]:
    if alert.fire_event_id:
        event = session.get(FireEvent, alert.fire_event_id)
        if event and event.zone is not None:
            return int(event.zone)
    if alert.risky_device_id:
        risky = session.get(RiskyDevice, alert.risky_device_id)
        if risky and risky.zone is not None:
            return int(risky.zone)
    return None


def frame_url_for_alert(session: Session, alert: Alert) -> Optional[str]:
    if alert.fire_event_id:
        event = session.get(FireEvent, alert.fire_event_id)
        if event and event.frame:
            return public_frame_url(event.frame)
    if alert.risky_device_id:
        risky = session.get(RiskyDevice, alert.risky_device_id)
        if risky and risky.frame:
            return public_frame_url(risky.frame)
    return None


def confidence_for_alert(session: Session, alert: Alert) -> Optional[float]:
    if alert.fire_event_id:
        event = session.get(FireEvent, alert.fire_event_id)
        if event and event.confidence is not None:
            return float(event.confidence)
    if alert.risky_device_id:
        risky = session.get(RiskyDevice, alert.risky_device_id)
        if risky and risky.confidence is not None:
            return float(risky.confidence)
    return None


def _zone_label(zone: Optional[int]) -> str:
    if zone is None:
        return "Zone: unknown"
    return f"Zone: {zone}"


@dataclass
class AlertNotifyContext:
    alert_id: int
    alert_type: str
    title: str
    plain_body: str
    html_body: str
    sms_body: str
    zone: Optional[int]
    frame_url: Optional[str]
    confidence_percent: Optional[int]


def build_alert_notify_context(
    session: Session,
    alert: Alert,
    confidence: Optional[float],
) -> AlertNotifyContext:
    resolved_conf = confidence if confidence is not None else confidence_for_alert(session, alert)
    _, percent = format_confidence(resolved_conf)
    zone = zone_for_alert(session, alert)
    frame_url = frame_url_for_alert(session, alert)
    label = alert_type_value(alert.alert_type).replace("_", " ").title()
    conf_part = f" — {percent}% confidence" if percent is not None else ""
    zone_part = f" — {_zone_label(zone)}" if zone is not None else ""

    title = f"{label}{zone_part}{conf_part}".strip(" —")
    plain_lines = [
        title,
        _zone_label(zone),
        f"Confidence: {percent}%" if percent is not None else "Confidence: n/a",
        f"Alert ID: {alert.id}",
        f"Time (UTC): {datetime.utcnow().isoformat()}",
    ]
    plain_body = "\n".join(plain_lines)

    img_html = ""
    if frame_url:
        safe_url = html.escape(frame_url, quote=True)
        img_html = (
            f'<p><img src="{safe_url}" alt="Detection frame" '
            f'style="max-width:100%;height:auto;border-radius:8px;" /></p>'
        )

    html_body = f"""<html><body>
<p><strong>{html.escape(title)}</strong></p>
<p>{html.escape(_zone_label(zone))}</p>
<p>Confidence: {percent if percent is not None else "n/a"}%</p>
<p>Alert ID: {alert.id}</p>
{img_html}
</body></html>"""

    sms_body = title
    if percent is not None:
        sms_body = f"{sms_body} ({percent}%)"

    return AlertNotifyContext(
        alert_id=alert.id,
        alert_type=alert_type_value(alert.alert_type),
        title=title,
        plain_body=plain_body,
        html_body=html_body,
        sms_body=sms_body,
        zone=zone,
        frame_url=frame_url,
        confidence_percent=percent,
    )


def alert_to_dict(alert: Alert) -> Dict[str, Any]:
    return {
        "id": alert.id,
        "alert_type": alert_type_value(alert.alert_type),
        "risky_device_id": alert.risky_device_id,
        "fire_event_id": alert.fire_event_id,
        "sensor_reading_id": alert.sensor_reading_id,
        "created_at": alert.created_at.isoformat() if isinstance(alert.created_at, datetime) else alert.created_at,
        "resolved_at": (
            alert.resolved_at.isoformat()
            if isinstance(alert.resolved_at, datetime)
            else alert.resolved_at
        ),
    }


def alert_to_ws_payload(session: Session, alert: Alert) -> Dict[str, Any]:
    payload = alert_to_dict(alert)
    payload["frame_url"] = frame_url_for_alert(session, alert)
    payload["zone"] = zone_for_alert(session, alert)
    return payload
