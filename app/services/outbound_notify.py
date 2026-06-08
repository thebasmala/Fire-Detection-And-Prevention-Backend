"""SendGrid (HTML + image), Twilio MMS, and FCM for high-confidence alerts."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from sqlmodel import Session, select

from app.config import settings
from app.core.storage import cloudinary_configured
from app.database import engine
from app.models.alert import Alert
from app.models.user import User
from app.services.alert_utils import (
    build_alert_notify_context,
    confidence_for_alert,
    format_confidence,
)
from app.services.fcm_service import fcm_configured, send_push

logger = logging.getLogger(__name__)

_last_external_notify_at: Optional[datetime] = None


def _sendgrid_ready() -> bool:
    return bool(
        (settings.sendgrid_api_key or "").strip()
        and (settings.sendgrid_from_email or "").strip()
    )


def _twilio_ready() -> bool:
    return bool(
        (settings.twilio_account_sid or "").strip()
        and (settings.twilio_auth_token or "").strip()
        and (settings.twilio_from_number or "").strip()
    )


def outbound_channels_status() -> Dict[str, Any]:
    return {
        "sendgrid_configured": _sendgrid_ready(),
        "twilio_configured": _twilio_ready(),
        "cloudinary_configured": cloudinary_configured(),
        "fcm_configured": fcm_configured(),
        "high_confidence_threshold": settings.high_confidence_threshold,
        "high_confidence_threshold_percent": int(
            round(settings.high_confidence_threshold * 100)
        ),
        "high_confidence_notify_cooldown_seconds": settings.high_confidence_notify_cooldown_seconds,
    }


def _cooldown_ok() -> bool:
    global _last_external_notify_at
    cooldown = max(0, int(settings.high_confidence_notify_cooldown_seconds))
    if cooldown == 0:
        return True
    now = datetime.utcnow()
    if _last_external_notify_at is None:
        return True
    return (now - _last_external_notify_at).total_seconds() >= cooldown


def _mark_sent() -> None:
    global _last_external_notify_at
    _last_external_notify_at = datetime.utcnow()


async def _send_email_html(
    *,
    to_email: str,
    subject: str,
    plain_body: str,
    html_body: str,
) -> bool:
    if not _sendgrid_ready():
        return False
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": settings.sendgrid_from_email.strip()},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": plain_body},
            {"type": "text/html", "value": html_body},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {settings.sendgrid_api_key.strip()}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code in (200, 202):
            logger.info("SendGrid email (with image) sent to %s", to_email)
            return True
        logger.warning(
            "SendGrid HTTP %s for %s: %s",
            response.status_code,
            to_email,
            (response.text or "")[:300],
        )
    except Exception as exc:
        logger.warning("SendGrid failed for %s: %s", to_email, exc)
    return False


async def _send_sms_mms(
    *,
    to_phone: str,
    body: str,
    media_url: Optional[str] = None,
) -> bool:
    if not _twilio_ready():
        return False
    sid = settings.twilio_account_sid.strip()
    token = settings.twilio_auth_token.strip()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data: Dict[str, str] = {
        "From": settings.twilio_from_number.strip(),
        "To": to_phone,
        "Body": body[:1600],
    }
    if media_url:
        data["MediaUrl"] = media_url
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, auth=(sid, token), data=data)
        if response.status_code in (200, 201):
            kind = "MMS" if media_url else "SMS"
            logger.info("Twilio %s sent to %s", kind, to_phone)
            return True
        logger.warning(
            "Twilio HTTP %s for %s: %s",
            response.status_code,
            to_phone,
            (response.text or "")[:300],
        )
    except Exception as exc:
        logger.warning("Twilio failed for %s: %s", to_phone, exc)
    return False


async def notify_high_confidence_users(*, alert_id: int, confidence: float) -> None:
    """Email (HTML image), SMS/MMS, and FCM when confidence >= threshold."""
    c, percent = format_confidence(confidence)
    if c is None or c < settings.high_confidence_threshold:
        return
    if not _cooldown_ok():
        logger.info("Skip outbound notify: cooldown active (%ss)", settings.high_confidence_notify_cooldown_seconds)
        return
    if not _sendgrid_ready() and not _twilio_ready() and not fcm_configured():
        logger.warning("Skip outbound: no SendGrid, Twilio, or Firebase configured")
        return

    try:
        with Session(engine) as session:
            alert = session.get(Alert, alert_id)
            if not alert:
                return
            resolved_conf = confidence_for_alert(session, alert) or c
            ctx = build_alert_notify_context(session, alert, resolved_conf)
            subject = f"[Fire System] {ctx.title}"

            users: List[User] = list(
                session.exec(select(User).where(User.is_active == True)).all()
            )
            sent = False

            for user in users:
                if user.notify_email and _sendgrid_ready():
                    if await _send_email_html(
                        to_email=user.email,
                        subject=subject,
                        plain_body=ctx.plain_body,
                        html_body=ctx.html_body,
                    ):
                        sent = True
                if user.notify_sms and user.phone_number and _twilio_ready():
                    if await _send_sms_mms(
                        to_phone=user.phone_number.strip(),
                        body=ctx.sms_body,
                        media_url=ctx.frame_url,
                    ):
                        sent = True
                if user.notify_push and user.fcm_token:
                    if not fcm_configured():
                        logger.warning(
                            "User %s has FCM token but Firebase is not configured on this server",
                            user.id,
                        )
                    elif send_push(
                        fcm_token=user.fcm_token,
                        title=ctx.title,
                        body=ctx.plain_body.split("\n")[0],
                        image_url=ctx.frame_url,
                        data={
                            "alert_id": ctx.alert_id,
                            "alert_type": ctx.alert_type,
                            "zone": str(ctx.zone) if ctx.zone is not None else "",
                            "confidence_percent": ctx.confidence_percent or "",
                            "event": "alert_created",
                        },
                    ):
                        sent = True

            if sent:
                _mark_sent()
            elif percent is not None:
                logger.warning(
                    "Outbound notify attempted for alert %s (%s%%) but no channel succeeded",
                    alert_id,
                    percent,
                )
    except Exception as exc:
        logger.warning("High-confidence notify error (non-fatal): %s", exc)
