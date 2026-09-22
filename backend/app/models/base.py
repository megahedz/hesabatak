"""
Base setup: SQLAlchemy engine/session + shared mixin columns.

NOTE ON MONEY: we never use float for money. All monetary columns are
Numeric(18, 2) which SQLAlchemy maps to Python's Decimal. Decimal avoids
the binary floating-point rounding errors that are unacceptable in
accounting software.
"""
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, DateTime, String, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker

# Default to SQLite for local/offline app + dev/testing.
# In production (server side, if a cloud sync backend is added later),
# point DATABASE_URL at Postgres instead, e.g.:
#   postgresql+psycopg2://user:pass@host:5432/hesabatak
DATABASE_URL = "sqlite:///./hesabatak.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class TimestampMixin:
    """created_at / updated_at / deleted_at (soft delete) — required on every table per spec §6."""
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class CompanyScopedMixin:
    """company_id — required on every business table per spec §6/§7 for multi-company isolation."""
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
