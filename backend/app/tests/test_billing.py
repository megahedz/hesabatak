"""Phase 8: الاشتراك — التجربة المجانية، الحالة المحسوبة، والصلاحيات.

كل شيء عبر HTTP فعلي (TestClient) كما باقي الاختبارات. الاشتراك يُسجَّل في
قاعدة البيانات (جدول subscriptions) والحالة تُحسب من الفترة والتاريخ.
"""
import os
os.environ.setdefault("HESABATAK_ALLOW_DEV_SECRET", "1")

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.models.base import Base, engine, SessionLocal
from app.main import app
from app.models.company import Company, User, CompanyUser
from app.models.billing import Subscription

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _register_and_company(idx: int) -> tuple[dict, int]:
    """Register a user + company over HTTP, return (headers, company_id)."""
    phone = f"0109{idx:08d}"
    email = f"user{idx}@example.com"
    res = client.post("/auth/register", params={
        "full_name": f"مالك {idx}", "phone": phone, "email": email,
        "password": "secret123",
    })
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/companies", params={"name": f"شركة {idx}"}, headers=headers)
    assert res.status_code == 200, res.text
    return headers, res.json()["id"]


def test_new_company_starts_in_free_trial():
    headers, cid = _register_and_company(1)
    res = client.get(f"/billing/status/{cid}", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "trialing"
    # الشركة أُنشئت لحظة فحص الحالة؛ (trial_end - now) قد يقصّ ثوانٍ إلى 13.
    assert data["days_left"] in (13, 14)
    assert data["provider"] == "manual"


def test_manual_activation_is_persisted_and_computed_active():
    headers, cid = _register_and_company(2)
    db = SessionLocal()
    sub = Subscription(
        company_id=cid, status="active", provider="manual", plan="monthly",
        amount=100, current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(sub)
    db.commit()
    db.close()

    data = client.get(f"/billing/status/{cid}", headers=headers).json()
    assert data["status"] == "active"
    assert data["plan"] == "monthly"
    assert data["provider"] == "manual"
    # بيانات الاشتراك محفوظة فعلًا في قاعدة البيانات (شرط المستخدم: الحفظ في DB)
    db = SessionLocal()
    row = db.query(Subscription).filter(Subscription.company_id == cid).first()
    assert row is not None and row.status == "active" and row.amount == 100
    db.close()


def test_expired_subscription_is_past_due():
    headers, cid = _register_and_company(3)
    db = SessionLocal()
    db.add(Subscription(
        company_id=cid, status="active", provider="manual",
        current_period_end=datetime.now(timezone.utc) - timedelta(days=1),
    ))
    db.commit()
    db.close()
    data = client.get(f"/billing/status/{cid}", headers=headers).json()
    assert data["status"] == "past_due"


def test_billing_status_requires_login():
    headers, cid = _register_and_company(4)
    res = client.get(f"/billing/status/{cid}")
    assert res.status_code == 401


def test_non_member_cannot_read_billing_status():
    _, cid = _register_and_company(5)
    other_headers, _ = _register_and_company(6)
    res = client.get(f"/billing/status/{cid}", headers=other_headers)
    assert res.status_code == 404  # لا تسريب وجود الشركة


def test_checkout_without_stripe_key_gives_clear_arabic_message():
    headers, cid = _register_and_company(7)
    assert os.environ.get("STRIPE_SECRET_KEY", "") == ""
    res = client.post(f"/billing/checkout/{cid}", headers=headers)
    assert res.status_code == 400
    assert "الدفع" in res.json()["detail"]
