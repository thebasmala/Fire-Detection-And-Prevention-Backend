"""Dashboard / Flutter WebSocket — alerts + sensor readings."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from app.config import settings
from app.core.security import get_current_active_user
from app.schemas.auth_session import RealtimeSettingsRead
from app.core.ws_auth import extract_ws_token, validate_ws_token
from app.core.ws_manager import ws_manager
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/realtime", tags=["Realtime"])


@router.get("/settings", response_model=RealtimeSettingsRead)
async def get_notification_client_settings(
    current_user: User = Depends(get_current_active_user),
):
    threshold = settings.high_confidence_threshold
    return RealtimeSettingsRead(
        high_confidence_threshold=threshold,
        high_confidence_notify_cooldown_seconds=settings.high_confidence_notify_cooldown_seconds,
        high_confidence_percent=int(round(threshold * 100)),
    )


@router.websocket("/ws")
async def dashboard_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(
        None,
        description="Optional JWT; web clients can omit if logged in (cookie is set on login)",
    ),
):
    """
    Real-time feed after login.

    Auth (automatic):
    - **Web:** ``POST /api/auth/login`` sets HttpOnly ``access_token`` cookie → connect
      ``ws://host/api/realtime/ws`` with no query string (same site).
    - **Flutter:** store ``access_token`` from login JSON →
      ``ws://host/api/realtime/ws?token=<access_token>`` or ``Authorization: Bearer`` header.

    Events (no filtering — dashboard shows all):
    - ``alert_created`` / ``alert_updated`` — ``data`` includes alert columns + ``frame_url``
    - ``sensor_reading`` — live sensor values
  """
    resolved = extract_ws_token(websocket) or token
    if not validate_ws_token(resolved):
        await websocket.close(code=1008, reason="Invalid or missing token — login first")
        return

    await ws_manager.connect(websocket)
    try:
        await websocket.send_json(
            {
                "event": "connected",
                "clients": ws_manager.connection_count,
                "auth": "ok",
            }
        )
        while True:
            data = await websocket.receive_text()
            if data.strip().lower() == "ping":
                await websocket.send_json({"event": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("WebSocket session ended: %s", exc)
    finally:
        await ws_manager.disconnect(websocket)
