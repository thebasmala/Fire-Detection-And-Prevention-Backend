import logging

from sqlalchemy import inspect, text
from sqlmodel import SQLModel, Session, create_engine

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

_USER_NOTIFY_COLUMNS = (
    ("notify_email", "BOOLEAN DEFAULT TRUE"),
    ("notify_sms", "BOOLEAN DEFAULT FALSE"),
    ("notify_push", "BOOLEAN DEFAULT TRUE"),
    ("phone_number", "VARCHAR"),
    ("fcm_token", "VARCHAR"),
)


def _migrate_user_notification_columns() -> None:
    """Add notification preference columns if the user table predates them."""
    try:
        insp = inspect(engine)
        if "user" not in insp.get_table_names():
            return
        existing = {c["name"] for c in insp.get_columns("user")}
    except Exception as exc:
        logger.warning("Could not inspect user table for migrations: %s", exc)
        existing = set()

    for col_name, col_type in _USER_NOTIFY_COLUMNS:
        if col_name in existing:
            continue
        stmt = f'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS {col_name} {col_type}'
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
            logger.info('Added user column "%s"', col_name)
        except Exception as exc:
            logger.error('Failed to add user column "%s": %s', col_name, exc)


def _backfill_user_notification_defaults() -> None:
    """Ensure existing rows get push/email defaults after column migration."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    'UPDATE "user" SET notify_push = TRUE WHERE notify_push IS NULL'
                )
            )
            conn.execute(
                text(
                    'UPDATE "user" SET notify_email = TRUE WHERE notify_email IS NULL'
                )
            )
    except Exception as exc:
        logger.debug("User notification backfill skipped: %s", exc)


def init_db():
    """Initialize database tables"""
    SQLModel.metadata.create_all(engine)
    _migrate_user_notification_columns()
    _backfill_user_notification_defaults()


def get_session():
    """Dependency for getting database session"""
    with Session(engine) as session:
        yield session
