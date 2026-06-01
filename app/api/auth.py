from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
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
from app.schemas.auth_session import AuthSessionResponse, SessionBootstrap, SessionUpdate
from app.schemas.user import LoginJsonRequest, UserCreate
from app.services.alert_utils import validate_phone_e164
from app.services.session_bootstrap import (
    apply_fcm_token,
    build_session_bootstrap,
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


def _authenticate_user(session: Session, username: str, password: str) -> User:
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
    response = JSONResponse(content=auth.model_dump(mode="json"))
    response.set_cookie(value=auth.access_token, **_token_cookie_kwargs())
    return response


def _apply_session_update(user: User, body: SessionUpdate) -> None:
    data = body.model_dump(exclude_unset=True)
    fcm = data.pop("fcm_token", None)
    apply_fcm_token(user, fcm)
    if "phone_number" in data:
        raw = data["phone_number"]
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            data["phone_number"] = None
        else:
            data["phone_number"] = validate_phone_e164(str(raw))
    for key, value in data.items():
        setattr(user, key, value)


@router.post("/register", response_model=AuthSessionResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    request: Request,
    session: Session = Depends(get_session),
):
    """Create account and sign in immediately."""
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
async def login(request: Request, session: Session = Depends(get_session)):
    """
    Login (web + mobile).

    - **Web / Swagger:** ``application/x-www-form-urlencoded`` with ``username`` and ``password``.
    - **Flutter:** ``application/json`` with ``username``, ``password``, and optional ``fcm_token``.
      The FCM token is obtained by your app from Firebase at runtime — end users never type it.
    """
    content_type = (request.headers.get("content-type") or "").lower()
    fcm_token: str | None = None

    if "application/json" in content_type:
        body = LoginJsonRequest.model_validate(await request.json())
        username, password = body.username, body.password
        fcm_token = body.fcm_token
    else:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        if not username or not password:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="username and password are required",
            )

    user = _authenticate_user(session, str(username), str(password))
    auth = _issue_auth_session(session, user, request, fcm_token=fcm_token)
    return _login_response(auth)


@router.get("/session", response_model=SessionBootstrap)
async def get_session(
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    """Refresh settings and URLs (cookie or Bearer)."""
    user = session.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return build_session_bootstrap(session, user, request)


@router.patch("/session", response_model=SessionBootstrap)
async def update_session(
    body: SessionUpdate,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Update notification prefs and/or register FCM device token.

    Flutter calls this automatically when Firebase rotates the push token — not user input.
    """
    user = session.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        _apply_session_update(user, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user.updated_at = datetime.utcnow()
    session.add(user)
    session.commit()
    session.refresh(user)
    return build_session_bootstrap(session, user, request)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(_COOKIE_NAME, path="/")
    return {"detail": "Logged out"}
