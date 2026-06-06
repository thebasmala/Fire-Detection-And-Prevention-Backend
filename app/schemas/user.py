from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    email: EmailStr
    username: str
    full_name: Optional[str] = None
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(min_length=6, examples=["secret123"])

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "admin@example.com",
                "username": "admin",
                "full_name": "Admin User",
                "password": "secret123",
                "is_active": True,
            }
        }
    )


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None


class UserRead(UserBase):
    id: int
    is_superuser: bool
    notify_email: bool = True
    notify_sms: bool = False
    notify_push: bool = True
    phone_number: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NotificationPreferencesRead(BaseModel):
    notify_email: bool
    notify_sms: bool
    notify_push: bool = True
    phone_number: Optional[str] = None
    has_fcm_token: bool = False

    class Config:
        from_attributes = True


class NotificationPreferencesUpdate(BaseModel):
    notify_email: Optional[bool] = None
    notify_sms: Optional[bool] = None
    notify_push: Optional[bool] = None
    phone_number: Optional[str] = None


class LoginJsonRequest(BaseModel):
    """JSON login — optional fcm_token is supplied by the mobile app from Firebase, not the user."""

    username: str = Field(examples=["admin"])
    password: str = Field(examples=["secret123"])
    fcm_token: Optional[str] = Field(
        default=None,
        description="FCM device token from Firebase SDK (mobile only)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "admin",
                "password": "secret123",
                "fcm_token": None,
            }
        }
    )
