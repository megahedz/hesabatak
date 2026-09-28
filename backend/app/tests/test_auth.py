"""
Exercises auth through the actual FastAPI app (TestClient), not by calling
Python functions directly — this is what proves the dependency wiring
(verify_company_access on every scoped route) actually works over HTTP,
not just in isolation.
"""
import os
os.environ.setdefault("HESABATAK_ALLOW_DEV_SECRET", "1")  # must be set before app.main is imported

import pytest
from fastapi.testclient import TestClient

from app.models.base import Base, engine
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _register(phone: str, name: str = "مستخدم", password: str = "secret123",
              email: str | None = None) -> str:
    """Each call gets a unique email unless one is passed explicitly."""
    if email is None:
        email = f"{phone}@example.com"
    res = client.post("/auth/register", params={"full_name": name, "phone": phone,
                                                "email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def test_register_and_login():
    token = _register("01000000001")
    assert token

    res = client.post("/auth/login", data={"username": "01000000001", "password": "secret123"})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_wrong_password_rejected():
    _register("01000000002")
    res = client.post("/auth/login", data={"username": "01000000002", "password": "wrong-password"})
    assert res.status_code == 401


def test_protected_route_requires_token():
    res = client.get("/companies/1/dashboard")
    assert res.status_code == 401


def test_creator_becomes_company_owner_and_can_use_it():
    token = _register("01000000003")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/companies", params={"name": "شركتي"}, headers=headers)
    assert res.status_code == 200
    company_id = res.json()["id"]

    res = client.get(f"/companies/{company_id}/dashboard", headers=headers)
    assert res.status_code == 200
    assert res.json()["رصيد_الخزينة"] == "0.00"

    res = client.post(f"/companies/{company_id}/operations/capital", params={"amount": "1000"}, headers=headers)
    assert res.status_code == 200


def test_user_cannot_access_another_users_company():
    token_a = _register("01000000004", name="مستخدم أ")
    token_b = _register("01000000005", name="مستخدم ب")

    res = client.post("/companies", params={"name": "شركة أ"}, headers={"Authorization": f"Bearer {token_a}"})
    company_a_id = res.json()["id"]

    # User B, with a valid token of their own, tries to reach User A's company.
    res = client.get(f"/companies/{company_a_id}/dashboard", headers={"Authorization": f"Bearer {token_b}"})
    assert res.status_code == 404  # not 403 — deliberately doesn't confirm the company exists

    # And can't post operations into it either.
    res = client.post(
        f"/companies/{company_a_id}/operations/capital",
        params={"amount": "500"}, headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res.status_code == 404


def test_list_my_companies_only_shows_own():
    token_a = _register("01000000006")
    token_b = _register("01000000007")
    client.post("/companies", params={"name": "شركة أ"}, headers={"Authorization": f"Bearer {token_a}"})
    client.post("/companies", params={"name": "شركة ب"}, headers={"Authorization": f"Bearer {token_b}"})

    res = client.get("/companies", headers={"Authorization": f"Bearer {token_a}"})
    names = [c["name"] for c in res.json()]
    assert names == ["شركة أ"]


def test_duplicate_phone_registration_rejected():
    _register("01000000008")
    res = client.post("/auth/register", params={"full_name": "آخر", "phone": "01000000008",
                                                "email": "other@example.com", "password": "whatever1"})
    assert res.status_code == 400


# ------------------------------------------------- البريد الإجباري + سياسة كلمة المرور
def test_register_without_email_rejected():
    res = client.post("/auth/register", params={"full_name": "بلا بريد", "phone": "01000000010",
                                                "password": "secret123"})
    assert res.status_code == 422  # FastAPI missing required query param


def test_register_invalid_email_rejected():
    for bad in ("not-an-email", "a@b", "a b@example.com", "@example.com"):
        res = client.post("/auth/register", params={"full_name": "صيغة خطأ", "phone": "01000000011",
                                                    "email": bad, "password": "secret123"})
        assert res.status_code == 400, bad


def test_register_duplicate_email_rejected_and_normalized():
    _register("01000000012", email="User@Example.com")
    # نفس البريد بأحرف كبيرة/فراغات يُطبَّع ويصطدم بالسجل الأول.
    res = client.post("/auth/register", params={"full_name": "مكرر", "phone": "01000000013",
                                                "email": "  USER@example.com ", "password": "secret123"})
    assert res.status_code == 400
    # بريد مختلف ينجح ويُخزَّن بحروف صغيرة.
    token = _register("01000000014", email="Clean@Example.COM")
    assert token


def test_weak_password_rejected():
    for weak in ("short1", "allletters", "12345678", "87654321"):
        res = client.post("/auth/register", params={"full_name": "ضعيف", "phone": "01000000015",
                                                    "email": "weak@example.com", "password": weak})
        assert res.status_code == 400, weak
    # حرف + رقم و8 أحرف → يُقبل.
    res = client.post("/auth/register", params={"full_name": "قوي", "phone": "01000000016",
                                                "email": "strong@example.com", "password": "abc12345"})
    assert res.status_code == 200, res.text


def test_me_returns_email():
    _register("01000000017", email="me@example.com")
    res = client.post("/auth/login", data={"username": "01000000017", "password": "secret123"})
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    me = client.get("/auth/me", headers=headers).json()
    assert me["email"] == "me@example.com"
