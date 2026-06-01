from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    email: EmailStr
    username: str
    full_name: Optional[str] = None
    is_active: bool = True


class UserCreate(UserBase):
    password: str


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


class FcmTokenUpdate(BaseModel):
    fcm_token: str


class LoginJsonRequest(BaseModel):
    """Mobile login — optional fcm_token is from Firebase SDK, not user input."""

    username: str
    password: str
    fcm_token: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None
