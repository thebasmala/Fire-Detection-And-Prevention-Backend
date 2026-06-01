"""WebSocket JWT from query string, Authorization header, or login cookie."""

from __future__ import annotations

from typing import Optional

from fastapi import WebSocket
from jose import JWTError, jwt

from app.config import settings


def extract_ws_token(websocket: WebSocket) -> Optional[str]:
    # 1) ?token= (Flutter / explicit clients)
    token = websocket.query_params.get("token")
    if token and token.strip():
        return token.strip()
    # 2) HttpOnly cookie set on POST /api/auth/login (web dashboard)
    cookie = websocket.cookies.get("access_token")
    if cookie and cookie.strip():
        return cookie.strip()
    # 3) Authorization: Bearer (some WebSocket clients)
    auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def username_from_ws_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        sub = payload.get("sub")
        return str(sub) if sub else None
    except JWTError:
        return None


def validate_ws_token(token: Optional[str]) -> bool:
    if not token:
        return False
    return username_from_ws_token(token) is not None
