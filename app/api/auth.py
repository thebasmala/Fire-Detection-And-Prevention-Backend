from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from app.config import settings
from app.core.security import (
    _COOKIE_NAME,
    create_access_token,
    get_current_active_user,
    get_password_hash,
    verify_password,
)
from app.database import get_session
from app.models.user import User
from app.schemas.auth_session import AuthSessionResponse, SessionBootstrap
from app.schemas.user import (
    FcmTokenUpdate,
    LoginJsonRequest,
    NotificationPreferencesRead,
    NotificationPreferencesUpdate,
    Token,
    UserCreate,
    UserRead,
)
from app.services.alert_utils import validate_phone_e164
from app.services.session_bootstrap import (
    apply_fcm_token,
    build_session_bootstrap,
    notification_preferences_for,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _token_cookie_kwargs() -> dict:
    return {
        "key": _COOKIE_NAME,
        "httponly": True,
        "max_age": settings.access_token_expire_minutes * 60,
        "samesite": "lax",
        "secure": settings.auth_cookie_secure,
        "path": "/",
    }


def _authenticate_user(
    session: Session,
    username: str,
    password: str,
) -> User:
    statement = select(User).where(User.username == username)
    user = session.exec(statement).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


def _issue_auth_session(
    session: Session,
    user: User,
    request: Request,
    *,
    fcm_token: str | None = None,
) -> AuthSessionResponse:
    apply_fcm_token(user, fcm_token)
    user.updated_at = datetime.utcnow()
    session.add(user)
    session.commit()
    session.refresh(user)

    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    bootstrap = build_session_bootstrap(session, user, request)
    return AuthSessionResponse(
        access_token=access_token,
        token_type="bearer",
        session=bootstrap,
    )


def _login_response(auth: AuthSessionResponse) -> JSONResponse:
    """JSON + HttpOnly cookie — web uses cookie for REST and WebSocket without copying JWT."""
    response = JSONResponse(content=auth.model_dump(mode="json"))
    response.set_cookie(value=auth.access_token, **_token_cookie_kwargs())
    return response


@router.post("/register", response_model=AuthSessionResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    request: Request,
    session: Session = Depends(get_session),
):
    """Create account and sign in immediately (same response as login)."""
    statement = select(User).where(User.email == user_data.email)
    if session.exec(statement).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    statement = select(User).where(User.username == user_data.username)
    if session.exec(statement).first():
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        email=user_data.email,
        username=user_data.username,
        full_name=user_data.full_name,
        hashed_password=get_password_hash(user_data.password),
        is_active=user_data.is_active,
        notify_email=True,
        notify_sms=False,
        notify_push=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    auth = _issue_auth_session(session, user, request)
    return _login_response(auth)


@router.post("/login", response_model=AuthSessionResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    """Form login (Swagger). Sets cookie + returns full session bootstrap."""
    user = _authenticate_user(session, form_data.username, form_data.password)
    auth = _issue_auth_session(session, user, request)
    return _login_response(auth)


@router.post("/login/json", response_model=AuthSessionResponse)
async def login_json(
    body: LoginJsonRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    """
    Flutter/mobile login. Pass optional ``fcm_token`` from Firebase SDK (automatic, not user-typed).
    """
    user = _authenticate_user(session, body.username, body.password)
    auth = _issue_auth_session(session, user, request, fcm_token=body.fcm_token)
    return _login_response(auth)


@router.get("/session", response_model=SessionBootstrap)
async def get_session_bootstrap(
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    """Refresh URLs/settings after app resume without re-entering credentials."""
    user = session.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return build_session_bootstrap(session, user, request)


@router.post("/logout")
async def logout(response: Response):
    """Clear auth cookie (web dashboard). Clients should also discard stored JWT."""
    response.delete_cookie(_COOKIE_NAME, path="/")
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserRead)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    return current_user


@router.get("/me/notification-preferences", response_model=NotificationPreferencesRead)
async def get_notification_preferences(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    user = session.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return notification_preferences_for(user)


@router.patch("/me/notification-preferences", response_model=NotificationPreferencesRead)
async def update_notification_preferences(
    prefs: NotificationPreferencesUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    user = session.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    data = prefs.model_dump(exclude_unset=True)
    if "phone_number" in data:
        raw = data["phone_number"]
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            data["phone_number"] = None
        else:
            try:
                data["phone_number"] = validate_phone_e164(str(raw))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    for key, value in data.items():
        setattr(user, key, value)
    user.updated_at = datetime.utcnow()
    session.add(user)
    session.commit()
    session.refresh(user)
    return notification_preferences_for(user)


@router.put("/me/fcm-token", response_model=NotificationPreferencesRead)
async def register_fcm_token(
    body: FcmTokenUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    """Called automatically when Firebase rotates the device token (not for manual entry)."""
    user = session.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    apply_fcm_token(user, body.fcm_token)
    if not user.fcm_token:
        raise HTTPException(status_code=400, detail="fcm_token cannot be empty")
    user.updated_at = datetime.utcnow()
    session.add(user)
    session.commit()
    session.refresh(user)
    prefs = notification_preferences_for(user)
    return NotificationPreferencesRead(
        notify_email=prefs.notify_email,
        notify_sms=prefs.notify_sms,
        notify_push=prefs.notify_push,
        phone_number=prefs.phone_number,
        has_fcm_token=True,
    )
