"""Dashboard / Flutter WebSocket — alerts + sensor readings."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.ws_auth import extract_ws_token, validate_ws_token
from app.core.ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/realtime", tags=["Realtime"])


@router.websocket("/ws")
async def dashboard_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(
        None,
        description="Flutter: pass JWT. Web: omit when login cookie is set.",
    ),
):
    """
    Real-time feed after login.

    - **Web:** cookie from ``POST /api/auth/login`` → connect without ``?token=``.
    - **Flutter:** ``?token=<access_token>`` from login response.
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
