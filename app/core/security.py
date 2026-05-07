from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select
from app.config import settings
from app.database import get_session
from app.models.user import User

# HTTPBearer: Swagger "Authorize" takes the JWT from POST /api/auth/login (OAuth2 Password flow alone does not).
_bearer_scheme = HTTPBearer(auto_error=True)
_fire_frame_bearer = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt"""
    # Generate salt and hash password
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


async def get_current_user(
    auth: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    """Get current authenticated user from JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = auth.credentials
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    statement = select(User).where(User.username == username)
    user = session.exec(statement).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def require_fire_frame_upload_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_fire_frame_bearer),
    x_fire_frame_key: Optional[str] = Header(None, alias="X-Fire-Frame-Key"),
    session: Session = Depends(get_session),
) -> None:
    """Pi uploads: set FIRE_FRAME_UPLOAD_API_KEY in .env and send X-Fire-Frame-Key, or use Bearer JWT."""
    if settings.fire_frame_upload_api_key and x_fire_frame_key == settings.fire_frame_upload_api_key:
        return
    if credentials and credentials.scheme.lower() == "bearer":
        try:
            payload = jwt.decode(
                credentials.credentials, settings.secret_key, algorithms=[settings.algorithm]
            )
            username: Optional[str] = payload.get("sub")
            if username:
                user = session.exec(select(User).where(User.username == username)).first()
                if user is not None and user.is_active:
                    return
        except JWTError:
            pass
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication for frame upload",
    )

