from sqlmodel import SQLModel, create_engine, Session
from app.config import settings

# Create database engine
engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)


def init_db():
    """Initialize database tables"""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Dependency for getting database session"""
    with Session(engine) as session:
        yield session

