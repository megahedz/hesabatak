"""
Base setup: SQLAlchemy engine/session + shared mixin columns.

ARCHITECTURE (mandatory): the cloud PostgreSQL database on the server is the
ONLY source of truth. The mobile app is a client that talks to this backend
over HTTPS — it never connects to Postgres directly and never stores
accounting data locally as a primary copy.

The connection string comes exclusively from the DATABASE_URL environment
variable (set on Render / your host, e.g. a Neon Postgres URL). Credentials
never live in the code or in the app. SQLite is only the zero-config fallback
for local development and the test suite.

NOTE ON MONEY: we never use float for money. All monetary columns are
Numeric(18, 2) which SQLAlchemy maps to Python's Decimal. Decimal avoids
the binary floating-point rounding errors that are unacceptable in
accounting software.
"""
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, Column, Integer, DateTime, String, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker


def resolve_database_url(raw: str | None = None) -> str:
    """Resolve the DB connection string from the environment.

    Accepted DATABASE_URL forms (what Neon/Render/Supabase hand you):
      postgresql://user:pass@host/db?sslmode=require
      postgres://user:pass@host/db            (legacy scheme, normalized)

    They are normalized to SQLAlchemy's psycopg2 driver form:
      postgresql+psycopg2://user:pass@host/db?sslmode=require

    sslmode=require is appended automatically for remote hosts that don't
    specify it, so production connections are always encrypted (TLS).
    With no DATABASE_URL set, we fall back to a local SQLite file — for
    development and the pytest suite only; production always sets it.
    """
    url = (raw if raw is not None else os.environ.get("DATABASE_URL", "")) or ""
    url = url.strip()
    if not url:
        return "sqlite:///./hesabatak.db"

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]

    if url.startswith("postgresql+psycopg2://") and "sslmode=" not in url:
        # host portion: everything after '@' up to '/' or ':'
        host = url.split("@", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        if host not in ("localhost", "127.0.0.1", "::1", "postgres", "db"):
            url += ("&" if "?" in url else "?") + "sslmode=require"

    return url


DATABASE_URL = resolve_database_url()
IS_POSTGRES = DATABASE_URL.startswith("postgresql")

engine = create_engine(
    DATABASE_URL,
    # SQLite needs this for FastAPI's threadpool; psycopg2 must NOT get it.
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    # Managed Postgres (Neon/Render) drops idle connections: pre-ping detects
    # dead connections transparently and recycle stays below their idle TTL.
    pool_pre_ping=True,
    pool_recycle=280,
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
