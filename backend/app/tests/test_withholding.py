"""ضريبة الخصم وفق قانون 91 لسنة 2005 (0.7.11).

تغطي: نِسَب الأنشطة (1% توريدات / 3% خدمات / 5% استشارات)، قيدَي البيع
والشراء المتوازنين مع حسابَي 1360/2160، حفظ النِسَب والمبالغ على الفاتورة،
الإعدادات (البطاقة الضريبية + تفعيل الضريبة)، ونقطة نهاية إشعار/شهادة الخصم
بصيغة PDF بخط عربي مضمّن.
"""
import os
os.environ.setdefault("HESABATAK_ALLOW_DEV_SECRET", "1")

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.models.base import Base, engine, SessionLocal
from app.main import app
from app.models import Customer, Supplier
from app.models.accounts import SystemAccountCode
from app.accounting.chart_of_accounts import seed_chart_of_accounts
from app.accounting.reports import general_ledger, trial_balance
from app.accounting.transactions import record_sale, record_purchase
from app.accounting.withholding import (
    WITHHOLDING_KINDS, amount_to_arabic_words, kind_rate, normalize_kind,
    withholding_for, WithholdingError,
)

client = TestClient(app)


def _setup_company():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client.post("/auth/register", params={"full_name": "مالك الضريبة",
                                          "phone": "01000000097",
                                          "email": "tax97@example.com",
                                          "password": "secret123"})
    token = client.post("/auth/login",
                        data={"username": "01000000097", "password": "secret123"}
                        ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    cid = client.post("/companies", params={"name": "محل الاختبار"}, headers=headers).json()["id"]
    return headers, cid


# ------------------------------------------------------------------ النِسَب
def test_kind_rates_are_1_3_5_percent():
    assert kind_rate("supply") == Decimal("1")
    assert kind_rate("service") == Decimal("3")
    assert kind_rate("consult") == Decimal("5")
    assert normalize_kind("توريدات") == "supply"
    assert normalize_kind("خدمات") == "service"
    assert normalize_kind("استشارات") == "consult"
    assert set(WITHHOLDING_KINDS) == {"supply", "service", "consult"}


def test_unknown_kind_and_bad_rate_are_rejected():
    with pytest.raises(WithholdingError):
        normalize_kind("مقاولات")
    with pytest.raises(WithholdingError):
        withholding_for(Decimal("100"), "supply", Decimal("150"))


def test_withholding_is_computed_on_the_amount_before_vat():
    amount, rate = withholding_for(Decimal("1000"), "service")
    assert amount == Decimal("30.00")
    assert rate == Decimal("3.00")
    # بلا نوع → بلا خصم (التفعيل اختياري لكل فاتورة)
    assert withholding_for(Decimal("1000"), None) == (Decimal("0.00"), Decimal("0.00"))


# --------------------------------------------------------- تحويل الحروف
@pytest.mark.parametrize("value,expected", [
    ("10", "عشرة جنيهات"),
    ("1000", "ألف جنيه"),
    ("15.50", "خمسة عشر جنيهًا وخمسون قرشًا"),
    ("0", "صفر جنيه"),
])
def test_amount_to_arabic_words(value, expected):
    assert amount_to_arabic_words(value).startswith(expected)


# ------------------------------------------------------------------ القيود
def _account_balance(db, cid, code):
    rep = general_ledger(db, cid, code)
    return rep["closing_balance"]


def test_sale_with_withholding_debits_1360_and_stays_balanced():
    headers, cid = _setup_company()
    db = SessionLocal()
    customer = Customer(company_id=cid, name="عميل الخصم"); db.add(customer); db.flush()
    inv = record_sale(db, company_id=cid, entry_date=date.today(),
                      amount=Decimal("1000"), is_credit=True,
                      customer_id=customer.id, vat_amount=Decimal("140"),
                      withholding_kind="supply")
    db.commit()

    assert inv.withholding_amount == Decimal("10.00")      # 1%
    assert inv.withholding_rate == Decimal("1.00")
    assert inv.withholding_kind == "supply"
    assert inv.total == Decimal("1140.00")

    # الحساب 1360 = ضريبة خصم تحت الحساب (مدين)
    assert _account_balance(db, cid, SystemAccountCode.WITHHOLDING_TAX_RECEIVABLE.value) == Decimal("10.00")
    # صافي المدين من العميل = 1140 - 10
    assert _account_balance(db, cid, SystemAccountCode.ACCOUNTS_RECEIVABLE.value) == Decimal("1130.00")
    assert trial_balance(db, cid)["is_balanced"]


def test_purchase_with_withholding_credits_2160():
    headers, cid = _setup_company()
    db = SessionLocal()
    supplier = Supplier(company_id=cid, name="مورد الخصم"); db.add(supplier); db.flush()
    inv = record_purchase(db, company_id=cid, entry_date=date.today(),
                          amount=Decimal("2000"), is_credit=True,
                          supplier_id=supplier.id, withholding_kind="consult")
    db.commit()

    assert inv.withholding_amount == Decimal("100.00")     # 5%
    assert inv.withholding_rate == Decimal("5.00")
    # دائن (رصيدنا للهيئة من المشتريات) — general_ledger يرجع الرصيد بالموجب
    assert _account_balance(db, cid, SystemAccountCode.WITHHOLDING_TAX_PAYABLE.value) == Decimal("100.00")
    assert trial_balance(db, cid)["is_balanced"]


def test_invoice_without_kind_has_no_withholding():
    headers, cid = _setup_company()
    db = SessionLocal()
    inv = record_sale(db, company_id=cid, entry_date=date.today(),
                      amount=Decimal("500"), is_credit=False)
    db.commit()
    assert inv.withholding_amount == Decimal("0.00")
    assert inv.withholding_kind is None


# ------------------------------------------------------- عبر الـ HTTP كاملًا
def test_settings_store_tax_card_and_toggle():
    headers, cid = _setup_company()
    res = client.post(f"/companies/{cid}/settings",
                      params={"tax_card_no": "234-567-891", "withholding_enabled": "true"},
                      headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["tax_card_no"] == "234-567-891"
    assert data["withholding_enabled"] is True


def test_sale_endpoint_accepts_withholding_and_notice_downloads():
    headers, cid = _setup_company()
    client.post(f"/companies/{cid}/settings", params={"tax_card_no": "111-222-333"},
                headers=headers)
    res = client.post(f"/companies/{cid}/operations/sale",
                      params={"amount": "1000", "is_credit": "false",
                              "withholding_kind": "service"},
                      headers=headers)
    assert res.status_code == 200, res.text
    invoice_id = res.json()["invoice_id"]

    db = SessionLocal()
    from app.models.documents import SalesInvoice
    inv = db.query(SalesInvoice).filter(SalesInvoice.id == invoice_id).one()
    assert inv.withholding_amount == Decimal("30.00")     # 3% خدمات

    notice = client.get(f"/companies/{cid}/withholding-notice/sale/{invoice_id}",
                        headers=headers)
    assert notice.status_code == 200, notice.text
    assert notice.headers["content-type"].startswith("application/pdf")
    assert notice.content.startswith(b"%PDF-1.")
    # خط عربي مضمّن + شعار الشركة داخل الورقة
    assert b"/FontFile2" in notice.content
    assert b"/DCTDecode" in notice.content
    assert "filename*=UTF-8''" in notice.headers["content-disposition"]


def test_notice_rejected_when_invoice_has_no_withholding():
    headers, cid = _setup_company()
    res = client.post(f"/companies/{cid}/operations/sale",
                      params={"amount": "100", "is_credit": "false"}, headers=headers)
    invoice_id = res.json()["invoice_id"]
    notice = client.get(f"/companies/{cid}/withholding-notice/sale/{invoice_id}",
                        headers=headers)
    assert notice.status_code == 400

    # نوع مستند مجهول → 404
    bad = client.get(f"/companies/{cid}/withholding-notice/zzz/{invoice_id}",
                     headers=headers)
    assert bad.status_code == 404


def test_backup_carries_withholding_fields():
    headers, cid = _setup_company()
    client.post(f"/companies/{cid}/settings",
                params={"tax_card_no": "999", "withholding_enabled": "true"},
                headers=headers)
    res = client.post(f"/companies/{cid}/operations/purchase",
                      params={"amount": "1000", "is_credit": "false",
                              "withholding_kind": "supply"}, headers=headers)
    assert res.status_code == 200, res.text

    backup = client.get(f"/companies/{cid}/backup", headers=headers).json()
    assert backup["company"]["tax_card_no"] == "999"
    assert backup["company"]["withholding_enabled"] is True
    assert backup["purchase_invoices"][0]["withholding_kind"] == "supply"
    assert backup["purchase_invoices"][0]["withholding_amount"] == "10.00"

    # الاستعادة تحفظها كما هي
    restored = client.post(f"/companies/{cid}/restore", json=backup, headers=headers)
    assert restored.status_code == 200, restored.text
    backup2 = client.get(f"/companies/{cid}/backup", headers=headers).json()
    assert backup2["purchase_invoices"][0]["withholding_amount"] == "10.00"
    assert backup2["company"]["withholding_enabled"] is True
