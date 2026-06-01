"""Firebase Cloud Messaging (FCM) push — optional; skips silently if not configured."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_firebase_initialized = False


def fcm_configured() -> bool:
    path = (settings.firebase_credentials_path or "").strip()
    return bool(path and Path(path).is_file())


def _ensure_firebase() -> bool:
    global _firebase_initialized
    if _firebase_initialized:
        return True
    if not fcm_configured():
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            cred = credentials.Certificate(settings.firebase_credentials_path.strip())
            firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        return True
    except Exception as exc:
        logger.warning("Firebase init failed (non-fatal): %s", exc)
        return False


def send_push(
    *,
    fcm_token: str,
    title: str,
    body: str,
    image_url: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> bool:
    if not fcm_token or not fcm_token.strip():
        return False
    if not _ensure_firebase():
        return False
    try:
        from firebase_admin import messaging

        notification = messaging.Notification(
            title=title[:200],
            body=body[:500],
            image=image_url if image_url else None,
        )
        payload_data = {str(k): str(v) for k, v in (data or {}).items() if v is not None}
        message = messaging.Message(
            notification=notification,
            data=payload_data,
            token=fcm_token.strip(),
        )
        messaging.send(message)
        logger.info("FCM push sent")
        return True
    except Exception as exc:
        logger.warning("FCM send failed (non-fatal): %s", exc)
        return False
