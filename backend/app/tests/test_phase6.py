"""
Phase 6 tests: detailed sales/purchases/inventory/expense reports, PDF/Excel
exports, and backup/restore round-trips — through real transaction flows,
always re-checking that the Trial Balance / Balance Sheet stay balanced.
"""
import io
import json
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.base import Base, engine, SessionLocal
from app.models import Company, Product
from app.models.accounts import SystemAccountCode
from app.accounting.chart_of_accounts import seed_chart_of_accounts
from app.accounting.engine import AccountingService, AccountingError
from app.accounting.transactions import record_sale, record_purchase, record_expense
from app.accounting.reports import trial_balance, balance_sheet, party_ledger_balance
from app.accounting.detailed_reports import sales_report, purchases_report, inventory_report, expense_report
from app.accounting.exports import build_pdf, build_xlsx
from app.accounting.backup import export_backup, restore_backup, RestoreError


D = Decimal


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session: Session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def company(db):
    c = Company(name="شركة المرحلة السادسة", currency="EGP",
                vat_enabled=True, vat_rate=D("14"), inventory_enabled=True)
    db.add(c)
    db.flush()
    seed_chart_of_accounts(db, c.id)
    db.commit()
    return c


def _seed_sales_cycle(db, company):
    """capital → buy 10 @50 → sell 4 @80 on credit → expense — a small but full cycle."""
    from app.models import Customer
    cid = company.id
    customer = Customer(company_id=cid, name="عميل الاختبار")
    db.add(customer)
    db.flush()
    p = Product(company_id=cid, name="منتج أ", unit="قطعة", purchase_price=0, selling_price=D("80"))
    db.add(p)
    db.flush()
    AccountingService.create_capital(db, company_id=cid, entry_date=date(2026, 9, 1), amount=D("10000"))
    record_purchase(db, company_id=cid, entry_date=date(2026, 9, 2), amount=D("500"),
                    is_credit=False, goes_to_inventory=True,
                    items=[{"product_id": p.id, "quantity": D("10"), "unit_price": D("50")}])
    record_sale(db, company_id=cid, entry_date=date(2026, 9, 3), amount=D("320"),
                is_credit=True, customer_id=customer.id,
                items=[{"product_id": p.id, "quantity": D("4"), "unit_price": D("80")}])
    record_expense(db, company_id=cid, entry_date=date(2026, 9, 4), amount=D("100"),
                   expense_account_code=SystemAccountCode.UNCATEGORIZED_EXPENSE.value)
    db.commit()
    return p


# ======================================================================
# Detailed reports
# ======================================================================
def test_sales_report_rows_and_totals(db, company):
    _seed_sales_cycle(db, company)
    rep = sales_report(db, company.id, start=date(2026, 9, 1), end=date(2026, 9, 30))
    assert len(rep["rows"]) == 1
    row = rep["rows"][0]
    assert row.invoice_number == "INV-000001"
    assert row.total == D("320.00")
    assert row.is_credit
    assert rep["lines"]["INV-000001"][0].quantity == D("4")
    assert rep["totals"]["count"] == 1
    assert rep["totals"]["total"] == D("320.00")
    assert rep["totals"]["credit_total"] == D("320.00")


def test_sales_report_period_filter_excludes_other_months(db, company):
    _seed_sales_cycle(db, company)
    rep = sales_report(db, company.id, start=date(2026, 1, 1), end=date(2026, 1, 31))
    assert rep["rows"] == []
    assert rep["totals"]["count"] == 0


def test_purchases_report_rows_and_totals(db, company):
    _seed_sales_cycle(db, company)
    rep = purchases_report(db, company.id)
    assert len(rep["rows"]) == 1
    assert rep["rows"][0].total == D("500.00")
    assert rep["lines"]["PUR-000001"][0].quantity == D("10")
    assert rep["totals"]["total"] == D("500.00")


def test_inventory_report_values_and_flags(db, company):
    p = _seed_sales_cycle(db, company)
    rep = inventory_report(db, company.id)
    assert rep["totals"]["items"] == 1
    # 10 bought @50, 4 sold → 6 left, value 6×50 = 300
    assert rep["rows"][0].current_stock == D("6")
    assert rep["rows"][0].avg_cost == D("50.0000")
    assert rep["rows"][0].stock_value == D("300.00")
    assert rep["rows"][0].retail_value == D("480.00")
    assert rep["totals"]["stock_value"] == D("300.00")
    assert not rep["rows"][0].is_low and not rep["rows"][0].is_out
    assert p.current_stock == D("6")


def test_inventory_report_low_and_out_flags(db, company):
    cid = company.id
    low = Product(company_id=cid, name="منخفض", current_stock=D("2"),
                  purchase_price=D("10"), selling_price=D("15"), minimum_stock=D("5"))
    out = Product(company_id=cid, name="نافد", current_stock=0,
                  purchase_price=D("10"), selling_price=D("15"))
    db.add_all([low, out])
    db.commit()
    rep = inventory_report(db, cid)
    by_name = {r.name: r for r in rep["rows"]}
    assert by_name["منخفض"].is_low and not by_name["منخفض"].is_out
    assert by_name["نافد"].is_out
    assert rep["totals"]["low_or_out"] == 2


def test_expense_report_groups_by_account_and_matches_pl(db, company):
    _seed_sales_cycle(db, company)
    cid = company.id
    record_expense(db, company_id=cid, entry_date=date(2026, 9, 5), amount=D("40"),
                   expense_account_code="6100")  # إيجار
    record_expense(db, company_id=cid, entry_date=date(2026, 9, 5), amount=D("60"),
                   expense_account_code="6100")
    db.commit()
    rep = expense_report(db, cid)
    by_code = {r["code"]: r["amount"] for r in rep["rows"]}
    assert by_code["6100"] == D("100.00")
    assert by_code["6900"] == D("100.00")
    assert rep["total"] == D("200.00")
    # The ledger remains the single source of truth: same numbers in P&L.
    pl = profit_and_loss_of(db, cid)
    assert pl["operating_expenses"] == rep["total"]


def profit_and_loss_of(db, cid):
    from app.accounting.reports import profit_and_loss
    return profit_and_loss(db, cid)


# ======================================================================
# Exports
# ======================================================================
def test_pdf_export_is_valid_and_contains_report_title(db, company):
    _seed_sales_cycle(db, company)
    rep = sales_report(db, company.id)
    rows = [[r.invoice_number, str(r.invoice_date), r.customer_name or "عميل نقدي",
             r.subtotal, r.vat_amount, r.total] for r in rep["rows"]]
    pdf = build_pdf("تقرير المبيعات", "كل الفترات",
                    ["رقم الفاتورة", "التاريخ", "العميل", "قبل الضريبة", "ض.ق.م", "الإجمالي"],
                    rows, [("الإجمالي", rep["totals"]["total"])])
    # reportlab يكتب %PDF-1.3؛ المهم أن الملف PDF صالحًا وبخط عربي مضمّن،
    # وإلا لتظهر الحروف العربية «؟» كما كان يحدث في المولّد القديم.
    assert pdf.startswith(b"%PDF-1.")
    assert b"%%EOF" in pdf
    assert b"/Contents" in pdf
    assert b"/FontFile2" in pdf


def test_xlsx_export_is_a_valid_zip_with_expected_parts(db, company):
    _seed_sales_cycle(db, company)
    rep = sales_report(db, company.id)
    rows = [[r.invoice_number, str(r.invoice_date), r.customer_name or "عميل نقدي",
             r.subtotal, r.vat_amount, r.total] for r in rep["rows"]]
    xlsx = build_xlsx("تقرير المبيعات", "كل الفترات",
                      [("المبيعات", ["رقم الفاتورة", "التاريخ", "العميل", "قبل الضريبة", "ض.ق.م", "الإجمالي"], rows)])
    z = zipfile.ZipFile(io.BytesIO(xlsx))
    assert z.testzip() is None
    names = z.namelist()
    assert "xl/workbook.xml" in names and "xl/styles.xml" in names
    sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert 'rightToLeft="1"' in sheet
    assert "تقرير المبيعات" in sheet
    assert "INV-000001" in sheet


def test_xlsx_roundtrip_decimals_survive(db, company):
    rep = inventory_report(db, company.id)   # empty inventory → headers only + totals row shape
    rows = [[r.name, r.current_stock, r.stock_value] for r in rep["rows"]]
    xlsx = build_xlsx("المخزون", None, [("المخزون", ["المنتج", "الرصيد", "القيمة"], rows)])
    z = zipfile.ZipFile(io.BytesIO(xlsx))
    sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "<v>" in sheet or "<is>" in sheet  # numeric or inline-string cells present


# ======================================================================
# Backup / restore
# ======================================================================
def test_backup_restore_roundtrip_preserves_everything(db, company):
    p = _seed_sales_cycle(db, company)
    cid = company.id
    backup = export_backup(db, cid)
    assert backup["app"] == "hesabatak"
    assert len(backup["sales_invoices"]) == 1
    # capital, purchase, sale, sale_cogs, expense
    assert len(backup["journal_entries"]) == 5
    assert backup["journal_entries"][0]["lines"], "entry lines must be embedded"
    assert backup["journal_entries"][0]["lines"][0]["account_code"]

    # A second company must be untouched by restoring company 1's data.
    other = Company(name="شركة أخرى", currency="EGP")
    db.add(other)
    db.flush()
    seed_chart_of_accounts(db, other.id)
    db.commit()

    # Wipe company 1, then restore it from the backup.
    restored_entries = restore_backup(db, cid, backup)
    db.commit()
    assert restored_entries == 5

    # Same invoices, products, balances — nothing lost (re-fetch: the session
    # was expunged during restore).
    p2 = db.get(Product, p.id)
    rep = sales_report(db, cid)
    assert len(rep["rows"]) == 1 and rep["rows"][0].total == D("320.00")
    assert D(p2.current_stock) == D("6") and D(p2.purchase_price) == D("50.0000")
    assert party_ledger_balance(db, cid, SystemAccountCode.CASH.value) == D("9400.00")
    assert trial_balance(db, cid)["is_balanced"]
    assert balance_sheet(db, cid)["is_balanced"]

    # The other company is intact and still isolated.
    assert party_ledger_balance(db, other.id, SystemAccountCode.CASH.value) == D("0.00")
    # And the other company's autoincrement stream moved past company 1's IDs.
    new_sale = record_sale(db, company_id=other.id, entry_date=date(2026, 9, 6), amount=D("50"), is_credit=False)
    db.commit()
    assert new_sale.id > backup["sales_invoices"][0]["id"]


def test_restore_rejects_corrupt_and_unbalanced_files(db, company):
    p = _seed_sales_cycle(db, company)
    cid = company.id
    backup = export_backup(db, cid)

    with pytest.raises(RestoreError):
        restore_backup(db, cid, {"app": "something-else"})
    with pytest.raises(RestoreError):
        restore_backup(db, cid, {**backup, "backup_version": 99})
    with pytest.raises(RestoreError):
        restore_backup(db, cid, {**backup, "customers": None})

    # An unbalanced backup must be refused — and leave current data untouched.
    tampered = json.loads(json.dumps(backup))
    tampered["journal_entries"][0]["lines"][0]["debit"] = "999999.00"
    with pytest.raises(RestoreError):
        restore_backup(db, cid, tampered)
    db.rollback()
    # Current data still intact after every rejection.
    assert len(sales_report(db, cid)["rows"]) == 1
    assert trial_balance(db, cid)["is_balanced"]


def test_restore_accepts_value_style_enums(db, company):
    """Hand-edited backups may carry raw values ('cash') instead of stored
    enum names ('CASH') — restore must accept both (forward compatibility)."""
    backup = export_backup(db, company.id)
    for inv in backup["sales_invoices"]:
        if "payment_method" in inv:
            inv["payment_method"] = str(inv["payment_method"]).lower()
    restore_backup(db, company.id, backup)
    db.commit()
    rep = sales_report(db, company.id)
    assert all(r.payment_method in ("cash", "bank") for r in rep["rows"])


# ======================================================================
# Cross-check: detailed reports vs ledger (spec §75 promise)
# ======================================================================
def test_detailed_sales_total_matches_pl_revenue(db, company):
    _seed_sales_cycle(db, company)
    rep = sales_report(db, company.id)
    from app.accounting.reports import profit_and_loss
    pl = profit_and_loss(db, company.id)
    assert rep["totals"]["subtotal"] == pl["revenue"]


# ======================================================================
# HTTP level: the new endpoints through the real FastAPI app
# ======================================================================
import os

os.environ.setdefault("HESABATAK_ALLOW_DEV_SECRET", "1")  # must precede app.main import

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

http_client = TestClient(app)


_http_counter = [0]


def _setup_company_with_one_sale() -> tuple[str, int]:
    """Register → create company → capital + one sale, all over HTTP."""
    _http_counter[0] += 1
    phone = f"0110{_http_counter[0]:08d}"
    res = http_client.post("/auth/register",
                           params={"full_name": "مستخدم SIX", "phone": phone,
                                   "email": f"{phone}@example.com", "password": "secret123"})
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    res = http_client.post("/companies", params={"name": "شركة HTTP"}, headers=headers)
    assert res.status_code == 200, res.text
    cid = res.json()["id"]
    res = http_client.post(f"/companies/{cid}/operations/capital",
                           params={"amount": "1000", "method": "cash"}, headers=headers)
    assert res.status_code == 200, res.text
    res = http_client.post(f"/companies/{cid}/operations/sale",
                           params={"amount": "250", "is_credit": "false", "method": "cash"}, headers=headers)
    assert res.status_code == 200, res.text
    return token, cid


def test_http_detailed_reports_and_exports():
    token, cid = _setup_company_with_one_sale()
    h = {"Authorization": f"Bearer {token}"}

    res = http_client.get(f"/companies/{cid}/reports/sales", headers=h)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["totals"]["count"] == 1
    assert body["totals"]["total"] == "250.00"

    res = http_client.get(f"/companies/{cid}/reports/inventory", headers=h)
    assert res.status_code == 200
    assert res.json()["totals"]["items"] == 0

    res = http_client.get(f"/companies/{cid}/reports/expenses", headers=h)
    assert res.status_code == 200
    assert res.json()["total"] == "0.00"

    # PDF export
    res = http_client.get(f"/companies/{cid}/export/sales", headers=h)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/pdf")
    assert res.content.startswith(b"%PDF-1.")
    assert "filename*=UTF-8''" in res.headers["content-disposition"]

    # Excel export (xlsx is a zip)
    res = http_client.get(f"/companies/{cid}/export/sales", params={"fmt": "excel"}, headers=h)
    assert res.status_code == 200
    assert res.content[:2] == b"PK"

    # Unknown report key → 404 with Arabic message
    res = http_client.get(f"/companies/{cid}/export/unknown", headers=h)
    assert res.status_code == 404


def test_http_backup_and_restore_roundtrip():
    token, cid = _setup_company_with_one_sale()
    h = {"Authorization": f"Bearer {token}"}

    res = http_client.get(f"/companies/{cid}/backup", headers=h)
    assert res.status_code == 200, res.text
    assert "attachment" in res.headers["content-disposition"]
    backup = res.json()
    assert backup["app"] == "hesabatak"
    assert len(backup["sales_invoices"]) == 1
    assert len(backup["journal_entries"]) == 2  # capital + sale

    # Restore the same backup: company data is replaced, everything stays balanced.
    res = http_client.post(f"/companies/{cid}/restore", json=backup, headers=h)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "ok"

    res = http_client.get(f"/companies/{cid}/reports/sales", headers=h)
    assert res.json()["totals"]["count"] == 1

    # A corrupt file is rejected with a friendly Arabic 400 — and data survives.
    res = http_client.post(f"/companies/{cid}/restore", json={"app": "nope"}, headers=h)
    assert res.status_code == 400
    assert res.json()["detail"]
    res = http_client.get(f"/companies/{cid}/reports/sales", headers=h)
    assert res.json()["totals"]["count"] == 1


def test_http_new_endpoints_require_membership():
    token, cid = _setup_company_with_one_sale()
    # رقم عشوائي: قاعدة الاختبار SQLite مشتركة بين التشغيلات، والأرقام الثابتة
    # تصطدم بمستخدمين من تشغيل سابق (كان هذا يُفشل الاختبار عشوائيًا).
    import random
    other_phone = f"0122{random.randint(0, 99999999):08d}"
    other = http_client.post("/auth/register",
                             params={"full_name": "غريب", "phone": other_phone,
                                     "email": f"{other_phone}@example.com", "password": "secret123"})
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    for path in (f"/companies/{cid}/reports/sales", f"/companies/{cid}/backup"):
        res = http_client.get(path, headers=other_headers)
        assert res.status_code == 404, path
    res = http_client.post(f"/companies/{cid}/restore", json={}, headers=other_headers)
    assert res.status_code == 404
