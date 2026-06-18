"""
Database engine and session management.

We use SQLAlchemy 2.0 style with a simple session-per-request pattern via
FastAPI's dependency injection (get_db below). This keeps the repository
layer (app/repositories/) free of any knowledge of how sessions are created
or torn down — repositories just receive a Session and use it.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models in app/models_db/."""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session, guarantees it closes after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
