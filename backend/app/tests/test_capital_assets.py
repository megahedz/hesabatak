"""0.7.13: رأس المال يُقسَّم نقدية + أصول مقدمة، ورقم فاتورة المورد.

تتحقق الاختبارات من:
  * create_capital بجزء أصول → قيد متوازن على 1500 «الأصول الثابتة».
  * نقطة HTTP /operations/capital تقبل assets_amount وتعيد الإجمالي.
  * فاتورة شراء تحمل supplier_invoice_no وتظهر في تقرير المشتريات.
  * النسخ الاحتياطي/الاستعادة يحفظ الرقم كما هو.
"""
import os
os.environ.setdefault("HESABATAK_ALLOW_DEV_SECRET", "1")

from datetime import date
from decimal import Decimal as D

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.base import Base, engine, SessionLocal
from app.models import Company
from app.models.accounts import SystemAccountCode
from app.models.documents import PurchaseInvoice
from app.accounting.chart_of_accounts import seed_chart_of_accounts
from app.accounting.engine import AccountingService, AccountingError
from app.accounting.reports import balance_sheet, trial_balance
from app.accounting.backup import export_backup, restore_backup
from app.main import app

client = TestClient(app)


def _fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _http_company():
    _fresh_db()
    client.post("/auth/register", params={"full_name": "مالك", "phone": "01000000097",
                                          "email": "owner97@example.com", "password": "secret123"})
    token = client.post("/auth/login", data={"username": "01000000097",
                                             "password": "secret123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    cid = client.post("/companies", params={"name": "شركة رأس المال"}, headers=headers).json()["id"]
    return headers, cid


def _engine_company(db: Session) -> Company:
    c = Company(name="شركة الأصول", currency="EGP")
    db.add(c)
    db.flush()
    seed_chart_of_accounts(db, c.id)
    db.commit()
    return c


def test_capital_with_assets_posts_cash_and_fixed_assets():
    """رأس المال = نقدي (1100) + أصول ثابتة (1500) في مدين، ورأس المال في دائن."""
    _fresh_db()
    db: Session = SessionLocal()
    try:
        cid = _engine_company(db).id
        AccountingService.create_capital(
            db, company_id=cid, entry_date=date(2026, 10, 1),
            amount=D("30000"), assets_amount=D("20000"),
            description="رأس مال افتتاحي (نقدية + أصول)",
        )
        db.commit()

        tb = trial_balance(db, cid)
        rows = {r.code: r for r in tb["rows"]}
        assert rows[SystemAccountCode.CASH.value].total_debit == D("30000.00")
        assert rows["1500"].total_debit == D("20000.00")
        assert rows[SystemAccountCode.OWNER_CAPITAL.value].total_credit == D("50000.00")
        assert tb["is_balanced"] is True

        bs = balance_sheet(db, cid)
        assert bs["is_balanced"], bs
    finally:
        db.close()


def test_capital_assets_zero_keeps_legacy_behaviour():
    """assets_amount=0 (السلوك القديم) → نقدي فقط برأس المال نفسه."""
    _fresh_db()
    db: Session = SessionLocal()
    try:
        cid = _engine_company(db).id
        AccountingService.create_capital(db, company_id=cid, entry_date=date(2026, 10, 1),
                                         amount=D("1000"))
        db.commit()
        tb = trial_balance(db, cid)
        rows = {r.code: r for r in tb["rows"]}
        assert rows[SystemAccountCode.CASH.value].total_debit == D("1000.00")
        assert rows[SystemAccountCode.OWNER_CAPITAL.value].total_credit == D("1000.00")
        assert "1500" not in rows   # صف بدون حركة لا يظهر أصلًا
    finally:
        db.close()


def test_negative_capital_rejected():
    _fresh_db()
    db: Session = SessionLocal()
    try:
        cid = _engine_company(db).id
        try:
            AccountingService.create_capital(db, company_id=cid, entry_date=date(2026, 10, 1),
                                             amount=D("1000"), assets_amount=D("-5"))
            raise AssertionError("negative assets must be rejected")
        except AccountingError:
            db.rollback()
    finally:
        db.close()


def test_http_capital_accepts_assets_amount():
    """POST /operations/capital + assets_amount → 200 والإجمالي في الرد."""
    headers, cid = _http_company()
    res = client.post(f"/companies/{cid}/operations/capital",
                      params={"amount": "30000", "assets_amount": "20000"},
                      headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "ok"
    assert D(data["total"]) == D("50000")
    assert D(data["cash_amount"]) == D("30000")
    assert D(data["assets_amount"]) == D("20000")

    db = SessionLocal()
    try:
        tb = trial_balance(db, cid)
        rows = {r.code: r for r in tb["rows"]}
        assert rows["1500"].total_debit == D("20000.00")
        assert rows[SystemAccountCode.OWNER_CAPITAL.value].total_credit == D("50000.00")
        assert tb["is_balanced"] is True
    finally:
        db.close()


def test_purchase_stores_supplier_invoice_no_and_reports_it():
    """فاتورة شراء تحمل رقم فاتورة المورد → محفوظة وفي تقرير المشتريات."""
    headers, cid = _http_company()
    res = client.post(
        f"/companies/{cid}/operations/purchase",
        params={"amount": "1500", "is_credit": "false", "method": "cash",
                "supplier_invoice_no": "SUP-7788"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    inv_number = res.json()["invoice_number"]

    rep = client.get(f"/companies/{cid}/reports/purchases", headers=headers)
    assert rep.status_code == 200, rep.text
    row = next(r for r in rep.json()["rows"] if r["invoice_number"] == inv_number)
    assert row["supplier_invoice_no"] == "SUP-7788"

    # بدون رقم → null (لا يُفرض شيء على العملاء القديم).
    res2 = client.post(f"/companies/{cid}/operations/purchase",
                       params={"amount": "200", "is_credit": "false", "method": "cash"},
                       headers=headers)
    assert res2.status_code == 200, res2.text
    rep2 = client.get(f"/companies/{cid}/reports/purchases", headers=headers)
    row2 = next(r for r in rep2.json()["rows"]
                if r["invoice_number"] == res2.json()["invoice_number"])
    assert row2["supplier_invoice_no"] is None


def test_supplier_invoice_no_survives_backup_restore():
    """رقم فاتورة المورد يخرج في النسخة الاحتياطية ويعود بعد الاستعادة."""
    headers, cid = _http_company()
    res = client.post(
        f"/companies/{cid}/operations/purchase",
        params={"amount": "900", "is_credit": "false", "method": "cash",
                "supplier_invoice_no": "INV-مورد-42"},
        headers=headers,
    )
    assert res.status_code == 200, res.text

    db = SessionLocal()
    try:
        payload = export_backup(db, cid)
        stored = [p for p in payload["purchase_invoices"]
                  if p.get("supplier_invoice_no") == "INV-مورد-42"]
        assert stored, payload["purchase_invoices"]

        restore_backup(db, cid, payload)   # يحذف ويبني من جديد بنفس المعرفات
        db.commit()
        inv = db.query(PurchaseInvoice).filter(
            PurchaseInvoice.supplier_invoice_no == "INV-مورد-42").one()
        assert inv.supplier_invoice_no == "INV-مورد-42"
    finally:
        db.close()


def test_supplier_invoice_no_is_truncated_to_50():
    headers, cid = _http_company()
    long_no = "X" * 80
    res = client.post(
        f"/companies/{cid}/operations/purchase",
        params={"amount": "100", "is_credit": "false", "method": "cash",
                "supplier_invoice_no": long_no},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    db = SessionLocal()
    try:
        inv = db.query(PurchaseInvoice).order_by(PurchaseInvoice.id.desc()).first()
        assert inv.supplier_invoice_no == "X" * 50
    finally:
        db.close()
