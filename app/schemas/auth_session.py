"""Post-login session payload for web and Flutter."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

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
    session: str


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


class SessionUpdate(BaseModel):
    """Optional push token (from Firebase in app code) and notification toggles."""

    fcm_token: Optional[str] = Field(
        default=None,
        description="FCM device token from Firebase SDK",
    )
    notify_email: Optional[bool] = None
    notify_sms: Optional[bool] = None
    notify_push: Optional[bool] = None
    phone_number: Optional[str] = Field(
        default=None,
        description="E.164 format, e.g. +201234567890",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "notify_email": True,
                "notify_push": True,
                "notify_sms": False,
                "phone_number": "+201234567890",
            }
        }
    )
