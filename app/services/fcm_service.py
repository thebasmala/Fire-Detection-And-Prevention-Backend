"""Firebase Cloud Messaging (FCM) push — optional; skips silently if not configured."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_firebase_initialized = False


def fcm_configured() -> bool:
    """True when the server can call Firebase Admin (required for push while app is closed)."""
    raw = (settings.firebase_credentials_json or "").strip()
    if raw:
        try:
            json.loads(raw)
            return True
        except json.JSONDecodeError:
            logger.warning("FIREBASE_CREDENTIALS_JSON is set but is not valid JSON")
            return False
    path = (settings.firebase_credentials_path or "").strip()
    return bool(path and Path(path).is_file())


def _load_certificate():
    from firebase_admin import credentials

    raw = (settings.firebase_credentials_json or "").strip()
    if raw:
        return credentials.Certificate(json.loads(raw))
    path = (settings.firebase_credentials_path or "").strip()
    if path and Path(path).is_file():
        return credentials.Certificate(path)
    return None


def _ensure_firebase() -> bool:
    global _firebase_initialized
    if _firebase_initialized:
        return True
    if not fcm_configured():
        return False
    try:
        import firebase_admin

        if not firebase_admin._apps:
            cred = _load_certificate()
            if cred is None:
                return False
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
        logger.warning(
            "FCM push skipped — configure FIREBASE_CREDENTIALS_PATH (local) or "
            "FIREBASE_CREDENTIALS_JSON (Railway) on the API server"
        )
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
