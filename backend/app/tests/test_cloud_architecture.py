"""
Cloud-architecture acceptance tests (mandatory architecture requirement):

  Android App → HTTPS API → Backend → Cloud PostgreSQL (single source of truth)

Covers:
  * The literal acceptance scenario from the requirement:
      create user → create company → create customer → create product
      → create invoice (sales + items) → record expense → record fixed asset
      → UNINSTALL/REINSTALL (a brand-new client with no session, no cache)
      → login with the SAME account → EVERYTHING is still there from the server.
  * DATABASE_URL plumbing: env parsing, postgres:// scheme normalization,
    sslmode injection, sqlite fallback (dev/tests only).
  * New mandatory entities: financial_years (auto-created with the company),
    fixed_assets, bank_accounts, cash_transactions/bank_transactions mirrors.
  * Production guard: HESABATAK_REQUIRE_POSTGRES=1 must refuse to boot on SQLite.
  * Backup roundtrip keeps the new entities and rebuilds the mirrors from the journal.
"""
import os
os.environ.setdefault("HESABATAK_ALLOW_DEV_SECRET", "1")  # must precede app.main import

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.models.base import Base, engine, SessionLocal, resolve_database_url
from app.main import app

client = TestClient(app)


@pytest.fixture()
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _register(phone: str) -> str:
    res = client.post("/auth/register", params={
        "full_name": "صاحب الشركة", "phone": phone,
        "email": f"{phone}@example.com", "password": "secret123",
    })
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


# ======================================================================
# DATABASE_URL plumbing
# ======================================================================

def test_database_url_env_parsing():
    """DATABASE_URL from env wins; postgres:// normalizes; sslmode injected
    for remote hosts; no DATABASE_URL → SQLite only for dev/tests."""
    assert resolve_database_url(None) == "sqlite:///./hesabatak.db"  # tests/dev only
    assert resolve_database_url("") == "sqlite:///./hesabatak.db"
    assert resolve_database_url("sqlite:///./x.db") == "sqlite:///./x.db"
    u = resolve_database_url("postgresql://u:p@ep-x.aws.neon.tech/neondb")
    assert u == "postgresql+psycopg2://u:p@ep-x.aws.neon.tech/neondb?sslmode=require"
    u2 = resolve_database_url("postgres://u:p@db.example.com/hes?sslmode=require")
    assert u2.startswith("postgresql+psycopg2://u:p@db.example.com/hes?sslmode=require")
    u3 = resolve_database_url("postgresql://u:p@localhost/hes")
    assert u3 == "postgresql+psycopg2://u:p@localhost/hes"  # local: no forced sslmode
    # Existing sslmode is preserved, not duplicated.
    u4 = resolve_database_url("postgresql://u:p@ep-x.aws.neon.tech/neondb?sslmode=require")
    assert u4.count("sslmode=") == 1


def test_production_refuses_sqlite(monkeypatch):
    """The mandatory guard: Render sets HESABATAK_REQUIRE_POSTGRES=1 — booting
    on SQLite must fail hard instead of silently storing data on an ephemeral
    disk (the exact data-loss bug this requirement fixes)."""
    import asyncio

    async def boom():
        raise RuntimeError("DATABASE_URL must point to a cloud PostgreSQL database")

    assert boom  # placeholder to keep the import meaningful
    from app.main import on_startup
    from app.models import base as base_mod

    monkeypatch.setattr(base_mod, "IS_POSTGRES", False)
    monkeypatch.setenv("HESABATAK_REQUIRE_POSTGRES", "1")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        on_startup()


# ======================================================================
# The literal acceptance scenario
# ======================================================================

def test_full_reinstall_scenario_data_survives(fresh_db):
    """إنشاء حساب → شركة → عميل → منتج → فاتورة بيع ببنود → مصروف → أصل ثابت
    → «إعادة تثبيت التطبيق» (عميل جديد تمامًا بلا جلسة ولا كاش)
    → دخول بنفس الحساب → كل البيانات السابقة موجودة من السيرفر."""
    # ---------- session 1 (before "uninstall") ----------
    token = _register("01055500001")
    h1 = {"Authorization": f"Bearer {token}"}

    cid = client.post("/companies", params={"name": "شركة الاختبار السحابي"}, headers=h1).json()["id"]

    cust = client.post(f"/companies/{cid}/customers", params={"name": "عميل محمود", "phone": "0123456789"},
                       headers=h1).json()
    prod = client.post(f"/companies/{cid}/products",
                       params={"name": "منتج أ", "purchase_price": "10", "selling_price": "15",
                               "opening_stock_qty": "20"},
                       headers=h1).json()

    items = [{"product_id": prod["id"], "quantity": 3, "unit_price": 15}]
    sale = client.post(f"/companies/{cid}/operations/sale",
                       params={"amount": "45", "is_credit": "false", "method": "cash",
                               "items_json": __import__("json").dumps(items)},
                       headers=h1).json()
    assert sale["invoice_number"].startswith("INV-")

    assert client.post(f"/companies/{cid}/operations/expense",
                       params={"amount": "30", "method": "cash", "notes": "كهرباء"},
                       headers=h1).status_code == 200

    asset = client.post(f"/companies/{cid}/assets",
                        params={"name": "ثلاجة عرض", "cost": "5000", "from_code": "1100"},
                        headers=h1).json()
    assert asset["id"] > 0

    bank = client.post(f"/companies/{cid}/bank-accounts",
                       params={"name": "البنك الأهلي", "account_number": "123456"},
                       headers=h1).json()
    assert bank["id"] > 0

    # Server-side truth before the "reinstall".
    db = SessionLocal()
    pre = {
        "customers": db.execute(__import__("sqlalchemy").text("SELECT COUNT(*) FROM customers WHERE company_id=:c"),
                                {"c": cid}).scalar(),
        "products": db.execute(__import__("sqlalchemy").text("SELECT COUNT(*) FROM products WHERE company_id=:c"),
                               {"c": cid}).scalar(),
        "sales": db.execute(__import__("sqlalchemy").text("SELECT COUNT(*) FROM sales_invoices WHERE company_id=:c"),
                            {"c": cid}).scalar(),
        "entries": db.execute(__import__("sqlalchemy").text("SELECT COUNT(*) FROM journal_entries WHERE company_id=:c"),
                              {"c": cid}).scalar(),
        "fy": db.execute(__import__("sqlalchemy").text("SELECT COUNT(*) FROM financial_years WHERE company_id=:c"),
                         {"c": cid}).scalar(),
        "assets": db.execute(__import__("sqlalchemy").text("SELECT COUNT(*) FROM fixed_assets WHERE company_id=:c"),
                             {"c": cid}).scalar(),
        "cash_tx": db.execute(__import__("sqlalchemy").text("SELECT COUNT(*) FROM cash_transactions WHERE company_id=:c"),
                              {"c": cid}).scalar(),
    }
    db.close()
    assert pre["customers"] == 1 and pre["products"] == 1 and pre["sales"] == 1
    assert pre["fy"] == 1 and pre["assets"] == 1 and pre["cash_tx"] >= 2

    # ---------- UNINSTALL / REINSTALL: a brand-new client, zero state ----------
    # Nothing client-side is reused: new token from a fresh login, no cache.
    token2 = _register_login_only = client.post("/auth/login",
                                                data={"username": "01055500001", "password": "secret123"})
    assert token2.status_code == 200, token2.text
    h2 = {"Authorization": f"Bearer {token2.json()['access_token']}"}

    # Same account → the SAME company comes back (not a new empty one).
    companies = client.get("/companies", headers=h2).json()
    assert [c["id"] for c in companies] == [cid], companies

    # 1) Company info survives.
    settings = client.get(f"/companies/{cid}/settings", headers=h2).json()
    assert settings["name"] == "شركة الاختبار السحابي"

    # 2) Customers survive with their details.
    customers = client.get(f"/companies/{cid}/customers", headers=h2).json()
    assert any(c["name"] == "عميل محمود" and c["phone"] == "0123456789" for c in customers), customers

    # 3) Products survive with stock reduced by the sale (20 - 3 = 17).
    products = client.get(f"/companies/{cid}/products", headers=h2).json()
    row = next(p for p in products if p["id"] == prod["id"])
    assert abs(float(row["current_stock"]) - 17.0) < 0.001, row

    # 4) Invoices survive (via the sales report, rebuilt from server data).
    sales_rep = client.get(f"/companies/{cid}/reports/sales", headers=h2).json()
    assert any(r["invoice_number"] == sale["invoice_number"] and r["total"] == "45.00"
               for r in sales_rep["rows"]), sales_rep["rows"]

    # 5) The fixed asset survives (real table now).
    assets = client.get(f"/companies/{cid}/assets", headers=h2).json()
    assert any(a["name"] == "ثلاجة عرض" and a["cost"] == "5000.00" for a in assets), assets

    # 6) Bank accounts survive.
    banks = client.get(f"/companies/{cid}/bank-accounts", headers=h2).json()
    assert any(b["name"] == "البنك الأهلي" for b in banks), banks

    # 7) Financial year exists and is listed.
    fys = client.get(f"/companies/{cid}/fiscal-years", headers=h2).json()
    assert len(fys) == 1 and fys[0]["start_date"] == f"{date.today().year}-01-01", fys

    # 8) Cash ledger reflects the server-side history: the cash sale (in),
    #    the expense (out) and the fixed-asset payment (transfer out).
    #    (البيع الآجل والمخزون الافتتاحي لا يمسان الخزينة أصلًا — الـ mirror أمين للقيود.)
    cash_tx = client.get(f"/companies/{cid}/cash-transactions", headers=h2).json()
    kinds = {t["reference_type"] for t in cash_tx}
    assert {"sale", "expense", "transfer"} <= kinds, cash_tx

    # 9) The dashboard numbers come back from the ledger exactly.
    dash = client.get(f"/companies/{cid}/dashboard", headers=h2).json()
    assert dash["مبيعات_الفترة"] == "45.00"

    # 10) Trial balance still balanced after everything.
    tb = client.get(f"/companies/{cid}/reports/trial-balance", headers=h2).json()
    assert tb["is_balanced"], tb


def test_new_company_gets_financial_year(fresh_db):
    token = _register("01055500002")
    h = {"Authorization": f"Bearer {token}"}
    cid = client.post("/companies", params={"name": "شركة السنة المالية"}, headers=h).json()["id"]
    fys = client.get(f"/companies/{cid}/fiscal-years", headers=h).json()
    assert len(fys) == 1
    assert fys[0]["is_closed"] is False
    # Idempotent: calling again doesn't duplicate.
    fys2 = client.get(f"/companies/{cid}/fiscal-years", headers=h).json()
    assert len(fys2) == 1


def test_fixed_asset_posts_real_journal_entry(fresh_db):
    token = _register("01055500003")
    h = {"Authorization": f"Bearer {token}"}
    cid = client.post("/companies", params={"name": "شركة الأصول"}, headers=h).json()["id"]

    res = client.post(f"/companies/{cid}/assets",
                      params={"name": "لابتوب", "cost": "20000", "from_code": "1200"}, headers=h)
    assert res.status_code == 200, res.text

    gl = client.get(f"/companies/{cid}/reports/general-ledger?account_code=1500", headers=h).json()
    assert gl["closing_balance"] == "20000.00", gl
    # And the cash/bank mirror caught the bank outflow too.
    bank_tx = client.get(f"/companies/{cid}/bank-transactions", headers=h).json()
    assert any(t["direction"] == "out" and t["amount"] == "20000.00" for t in bank_tx), bank_tx


def test_new_entities_included_in_backup_roundtrip(fresh_db):
    """Backup → restore keeps financial years / assets / bank accounts and
    rebuilds cash/bank mirrors from the restored journal."""
    token = _register("01055500004")
    h = {"Authorization": f"Bearer {token}"}
    cid = client.post("/companies", params={"name": "شركة النسخ"}, headers=h).json()["id"]

    client.post(f"/companies/{cid}/assets", params={"name": "مكتب", "cost": "1500"}, headers=h)
    client.post(f"/companies/{cid}/bank-accounts", params={"name": "بنك مصر"}, headers=h)

    backup = client.get(f"/companies/{cid}/backup", headers=h)
    assert backup.status_code == 200
    payload = backup.json()

    restore = client.post(f"/companies/{cid}/restore", json=payload, headers=h)
    assert restore.status_code == 200, restore.text

    assets = client.get(f"/companies/{cid}/assets", headers=h).json()
    assert any(a["name"] == "مكتب" for a in assets), assets
    banks = client.get(f"/companies/{cid}/bank-accounts", headers=h).json()
    assert any(b["name"] == "بنك مصر" for b in banks), banks
    cash_tx = client.get(f"/companies/{cid}/cash-transactions", headers=h).json()
    assert any(t["reference_type"] == "transfer" for t in cash_tx), cash_tx
    tb = client.get(f"/companies/{cid}/reports/trial-balance", headers=h).json()
    assert tb["is_balanced"], tb


def test_bank_accounts_and_cash_ledger_endpoints(fresh_db):
    token = _register("01055500005")
    h = {"Authorization": f"Bearer {token}"}
    cid = client.post("/companies", params={"name": "شركة البنوك"}, headers=h).json()["id"]

    # Bank account CRUD.
    assert client.post(f"/companies/{cid}/bank-accounts", params={"name": "CIB"}, headers=h).status_code == 200
    banks = client.get(f"/companies/{cid}/bank-accounts", headers=h).json()
    assert len(banks) == 1 and banks[0]["name"] == "CIB"

    # Date filtering on the cash ledger.
    rows = client.get(f"/companies/{cid}/cash-transactions",
                      params={"start": str(date.today()), "end": str(date.today())}, headers=h).json()
    assert isinstance(rows, list)
