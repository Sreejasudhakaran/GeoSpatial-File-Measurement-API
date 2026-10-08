"""
Database engine and session management.

Provides:
- SQLAlchemy engine configured from settings
- SessionLocal factory for request transactions
- get_db() dependency yielding a session and ensuring it closes
- create_tables() helper to initialize schema
- SQLite foreign key pragma listener ensuring CASCADE deletes work
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Base

# Configure engine options
# For SQLite, check_same_thread=False allows FastAPI threads to share the connection pool
connect_args: dict[str, bool] = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine: Engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
    """Enable foreign key constraints and cascade deletes in SQLite.

    SQLite has foreign key enforcement DISABLED by default for backwards compatibility.
    This event listener ensures 'PRAGMA foreign_keys=ON' runs on every SQLite connection.
    """
    # Check if the underlying DBAPI connection is sqlite3
    if "sqlite" in type(dbapi_connection).__module__:
        cursor = getattr(dbapi_connection, "cursor")()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a transactional SQLAlchemy session.

    Guarantees the session is always closed when the request lifecycle ends.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables(bind_engine: Engine | None = None) -> None:
    """Create all database tables registered in Base.metadata.

    Args:
        bind_engine: Optional engine override (useful for test suites).
    """
    target_engine = bind_engine or engine
    Base.metadata.create_all(bind=target_engine)
