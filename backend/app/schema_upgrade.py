"""
Startup column migration (no alembic in this project).

`Base.metadata.create_all()` only creates MISSING TABLES — it never adds a
column to an existing table. That is fine for a fresh database, but the
production PostgreSQL database (Neon) already has `companies`,
`sales_invoices`, `purchase_invoices` … so every column introduced in a new
release would be invisible there and every INSERT/SELECT would fail.

This module bridges that gap: at startup, right after create_all, it inspects
`information_schema` (via SQLAlchemy's inspector) and issues the minimal
`ALTER TABLE … ADD COLUMN` statements for columns that do not exist yet.

Safety rules:
  * only ADD COLUMN — never DROP, never CHANGE a type, never touches data;
  * every new column carries a constant DEFAULT and NOT NULL (Postgres 11+
    stores such defaults in the catalog only, so it is O(1) on a big table);
  * it is idempotent — a second run finds every column present and does
    nothing, which matters because startup runs on every deploy;
  * a table that does not exist yet is skipped (create_all will build it with
    the full model, columns included).
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.models.base import engine as default_engine, IS_POSTGRES

# table -> [(column, sql type, default literal or None for a nullable column)]
NEW_COLUMNS: dict[str, list[tuple[str, str, str | None]]] = {
    "users": [
        # login by e-mail (0.7.x) — older cloud rows were created before it.
        ("email", "VARCHAR(150)", None),
    ],
    "companies": [
        ("catalog_mode", "BOOLEAN", "FALSE" if IS_POSTGRES else "0"),
        ("tax_card_no", "VARCHAR(50)", None),
        ("withholding_enabled", "BOOLEAN", "FALSE" if IS_POSTGRES else "0"),
    ],
    "sales_invoices": [
        ("withholding_kind", "VARCHAR(20)", None),
        ("withholding_rate", "NUMERIC(5,2)", "0"),
        ("withholding_amount", "NUMERIC(18,2)", "0"),
    ],
    "purchase_invoices": [
        ("withholding_kind", "VARCHAR(20)", None),
        ("withholding_rate", "NUMERIC(5,2)", "0"),
        ("withholding_amount", "NUMERIC(18,2)", "0"),
    ],
}


def ensure_schema_columns(bind: Engine | None = None) -> list[str]:
    """Add every missing column from NEW_COLUMNS. Returns the ones added
    (empty list when the schema is already up to date)."""
    bind = bind or default_engine
    inspector = inspect(bind)
    added: list[str] = []
    with bind.begin() as conn:
        for table, columns in NEW_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, sql_type, default in columns:
                if name in existing:
                    continue
                ddl = f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"
                if default is not None:
                    ddl += f" DEFAULT {default} NOT NULL"
                conn.execute(text(ddl))
                added.append(f"{table}.{name}")
    return added
