"""Post-login session payload for web and Flutter."""

from pydantic import BaseModel

from app.schemas.user import NotificationPreferencesRead, UserRead


class RealtimeSettingsRead(BaseModel):
    high_confidence_threshold: float
    high_confidence_notify_cooldown_seconds: int
    high_confidence_percent: int


class ClientEndpoints(BaseModel):
    api_base: str
    websocket_path: str
    websocket_url: str
    alerts: str
    docs: str
    health: str
    notification_preferences: str
    session_refresh: str


class ClientFeatures(BaseModel):
    email_available: bool
    sms_available: bool
    push_available: bool
    cloudinary_available: bool
    push_registered: bool


class SessionBootstrap(BaseModel):
    user: UserRead
    notification_preferences: NotificationPreferencesRead
    realtime: RealtimeSettingsRead
    endpoints: ClientEndpoints
    features: ClientFeatures


class AuthSessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    session: SessionBootstrap
