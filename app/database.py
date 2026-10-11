
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


if not settings.DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing. Configure it in your local .env file."
    )

DATABASE_URL = settings.DATABASE_URL

# Accept Neon's standard URL format while using Psycopg 3.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"sslmode": "require"},
)


def ensure_task_columns():
    """Add task fields introduced after the initial database schema."""
    columns = {column["name"] for column in inspect(engine).get_columns("tasks")}
    with engine.begin() as connection:
        if "priority" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE tasks ADD COLUMN priority "
                    "VARCHAR(20) NOT NULL DEFAULT 'medium'"
                )
            )
        if "due_at" not in columns:
            connection.execute(
                text("ALTER TABLE tasks ADD COLUMN due_at TIMESTAMP WITH TIME ZONE")
            )

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    """Base class for Garuda Ops database models."""
    pass


def get_db():
    """Provide one database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
