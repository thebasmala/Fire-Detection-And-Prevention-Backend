"""WebSocket connection pool for dashboard real-time updates (multiple clients)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class _DateTimeJSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, Enum):
            return o.value
        return super().default(o)


class ConnectionManager:
    """Thread-safe broadcast to every connected dashboard WebSocket."""

    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info("Dashboard WebSocket connected (%s clients)", len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
        logger.info("Dashboard WebSocket disconnected (%s clients)", len(self._connections))

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        if not self._connections:
            return
        text = json.dumps(message, cls=_DateTimeJSONEncoder)
        async with self._lock:
            targets: List[WebSocket] = list(self._connections)
        dead: List[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(text)
            except Exception as exc:
                logger.debug("WebSocket send failed, dropping client: %s", exc)
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)

    def schedule_broadcast(self, message: Dict[str, Any]) -> None:
        """Safe to call from sync MQTT handlers on the main asyncio loop."""
        loop = self._loop
        if loop is None or not loop.is_running():
            logger.debug("No running event loop; skipping WebSocket broadcast")
            return
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
        except Exception as exc:
            logger.debug("Could not schedule WebSocket broadcast: %s", exc)


ws_manager = ConnectionManager()
