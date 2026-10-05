"""Unit tests for DATABASE_URL resolution + masked diagnostics (no live DB needed).

Covers the exact production failure mode seen on Render: DATABASE_URL missing
or pasted with wrapping quotes made IS_POSTGRES False and the startup guard
refused to boot — now the app explains itself in the log without leaking
credentials.
"""
import os

from app.models.base import database_diagnostics, resolve_database_url


def test_empty_env_falls_back_to_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert resolve_database_url() == "sqlite:///./hesabatak.db"
    assert resolve_database_url("") == "sqlite:///./hesabatak.db"
    assert resolve_database_url("   ") == "sqlite:///./hesabatak.db"


def test_legacy_scheme_normalized(monkeypatch):
    url = resolve_database_url("postgres://u:p@db.example.com/hesabatak")
    assert url == "postgresql+psycopg2://u:p@db.example.com/hesabatak?sslmode=require"


def test_quoted_value_is_stripped(monkeypatch):
    """The dashboard-paste accident: \"postgres://...\" with the quotes."""
    raw = '"postgresql://u:p@db.example.com/hesabatak?sslmode=require"'
    url = resolve_database_url(raw)
    assert url.startswith("postgresql+psycopg2://")
    assert "sslmode=require" in url

    single = resolve_database_url("'postgres://u:p@db.example.com/hesabatak'")
    assert single == "postgresql+psycopg2://u:p@db.example.com/hesabatak?sslmode=require"


def test_driver_form_kept_without_duplicate_sslmode(monkeypatch):
    raw = "postgresql+psycopg2://u:p@db.example.com/hesabatak?sslmode=require"
    assert resolve_database_url(raw) == raw


def test_sslmode_appended_for_remote_only(monkeypatch):
    url = resolve_database_url("postgresql://u:p@localhost/hesabatak")
    assert "sslmode=" not in url
    url = resolve_database_url("postgresql://u:p@db.example.com/hesabatak")
    assert url.endswith("sslmode=require")


def test_diagnostics_not_set(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    msg = database_diagnostics()
    assert "NOT set" in msg


def test_diagnostics_wrong_scheme_masks_credentials(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql://root:supersecret@host/db")
    msg = database_diagnostics()
    assert "mysql" in msg
    assert "supersecret" not in msg
    assert "host" not in msg


def test_diagnostics_ok_scheme(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db")
    msg = database_diagnostics()
    assert "postgresql" in msg
    assert "looks correct" in msg
