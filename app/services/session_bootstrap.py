"""Single post-login payload so clients never assemble tokens/URLs manually."""

from __future__ import annotations

from typing import Optional

from fastapi import Request
from sqlmodel import Session

from app.config import settings
from app.models.user import User
from app.schemas.auth_session import (
    ClientEndpoints,
    ClientFeatures,
    RealtimeSettingsRead,
    SessionBootstrap,
)
from app.schemas.user import NotificationPreferencesRead, UserRead
from app.services.outbound_notify import outbound_channels_status


def _api_base(request: Optional[Request]) -> str:
    if settings.public_api_base_url:
        return settings.public_api_base_url.rstrip("/")
    if request is not None:
        return str(request.base_url).rstrip("/")
    return f"http://{settings.host}:{settings.port}".rstrip("/")


def _websocket_urls(api_base: str) -> tuple[str, str]:
    path = "/api/realtime/ws"
    if api_base.startswith("https://"):
        full = api_base.replace("https://", "wss://", 1) + path
    elif api_base.startswith("http://"):
        full = api_base.replace("http://", "ws://", 1) + path
    else:
        full = f"ws://{api_base.lstrip('/')}{path}"
    return path, full


def _realtime_settings() -> RealtimeSettingsRead:
    threshold = settings.high_confidence_threshold
    return RealtimeSettingsRead(
        high_confidence_threshold=threshold,
        high_confidence_notify_cooldown_seconds=settings.high_confidence_notify_cooldown_seconds,
        high_confidence_percent=int(round(threshold * 100)),
    )


def notification_preferences_for(user: User) -> NotificationPreferencesRead:
    return NotificationPreferencesRead(
        notify_email=user.notify_email,
        notify_sms=user.notify_sms,
        notify_push=user.notify_push,
        phone_number=user.phone_number,
        has_fcm_token=bool((user.fcm_token or "").strip()),
    )


def build_session_bootstrap(
    session: Session,
    user: User,
    request: Optional[Request] = None,
) -> SessionBootstrap:
    """Everything a client needs after login — no manual token or URL assembly."""
    session.refresh(user)
    api_base = _api_base(request)
    ws_path, ws_full = _websocket_urls(api_base)
    channels = outbound_channels_status()
    prefs = notification_preferences_for(user)

    return SessionBootstrap(
        user=UserRead.model_validate(user),
        notification_preferences=prefs,
        realtime=_realtime_settings(),
        endpoints=ClientEndpoints(
            api_base=api_base,
            websocket_path=ws_path,
            websocket_url=ws_full,
            alerts=f"{api_base}/api/alerts",
            docs=f"{api_base}/docs",
            health=f"{api_base}/health",
            notification_preferences=f"{api_base}/api/auth/me/notification-preferences",
            session_refresh=f"{api_base}/api/auth/session",
        ),
        features=ClientFeatures(
            email_available=bool(channels.get("sendgrid_configured")),
            sms_available=bool(channels.get("twilio_configured")),
            push_available=bool(channels.get("fcm_configured")),
            cloudinary_available=bool(channels.get("cloudinary_configured")),
            push_registered=prefs.has_fcm_token and prefs.notify_push,
        ),
    )


def apply_fcm_token(user: User, fcm_token: Optional[str]) -> None:
    """Store device token from Firebase SDK (never typed by the end user)."""
    if not fcm_token:
        return
    token = fcm_token.strip()
    if token:
        user.fcm_token = token
