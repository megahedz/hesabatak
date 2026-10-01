#!/usr/bin/env python3
"""
تهيئة قاعدة البيانات السحابية (Neon/Render Postgres) — خطوة واحدة.

What it does (idempotent — safe to run more than once):
  1. Resolves DATABASE_URL from the environment (or --database-url) and
     REFUSES to run against SQLite — this script exists for the cloud DB.
  2. Creates every table (Base.metadata.create_all — same as the app's startup).
  3. Seeds the owner account (bcrypt-hashed password), the company, the full
     default chart of accounts, and the current financial year.

Usage (from backend/):
  export DATABASE_URL="postgresql://user:pass@host/db?sslmode=require"
  python3 scripts/init_cloud_db.py \
      --full-name "Megahed" --phone "Megahed" --email "megahed@hesabatak.app" \
      --password "..." --company "محل Megahed"

Or pass --database-url directly instead of the env var.
The password is never stored in plain text and is never printed.
"""
import argparse
import os
import sys
from datetime import date
from pathlib import Path

# Make `app` importable when run as a script from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed the cloud PostgreSQL database for حساباتك.")
    p.add_argument("--database-url", default=None,
                   help="PostgreSQL connection string (defaults to DATABASE_URL env var).")
    p.add_argument("--full-name", required=True, help="Owner display name.")
    p.add_argument("--phone", required=True, help="Login username (stored in users.phone).")
    p.add_argument("--email", required=True, help="Owner email (required by the API register policy).")
    p.add_argument("--password", required=True, help="Owner password (8+ chars, letter + digit). Stored hashed.")
    p.add_argument("--company", required=True, help="Company name to create.")
    return p.parse_args()


ARGS = _parse_args()

# The SQLAlchemy engine in app.models.base is built from DATABASE_URL at import
# time — exactly like the app's own startup. Inject the target URL into the
# environment BEFORE importing the app so the script and the app share ONE
# code path (no separate engine, no drift between seed and runtime).
if ARGS.database_url:
    os.environ["DATABASE_URL"] = ARGS.database_url

from app.models.base import resolve_database_url, engine  # noqa: E402
from app.models import Base, SessionLocal, User, Company, CompanyUser, Account  # noqa: E402
from app.accounting.chart_of_accounts import seed_chart_of_accounts  # noqa: E402
from app.auth.security import hash_password  # noqa: E402


def mask_url(url: str) -> str:
    """postgresql://user:secret@host/db -> postgresql://user:***@host/db"""
    if "@" not in url:
        return url
    scheme_user, host = url.split("@", 1)
    if ":" in scheme_user:
        scheme_user = scheme_user.rsplit(":", 1)[0] + ":***"
    return scheme_user + "@" + host


def main() -> int:
    db_url = resolve_database_url()
    if db_url.startswith("sqlite"):
        print("✗ رفض التنفيذ: DATABASE_URL غير مضبوط — هذا السكربت لقاعدة PostgreSQL السحابية فقط.")
        print("  مثال: postgresql://user:pass@ep-xxx-pooler.aws.neon.tech/neondb?sslmode=require")
        return 2
    if not db_url.startswith("postgresql"):
        print("✗ رابط غير متوقع (ليس postgresql) — توقف.")
        return 2

    print(f"• قاعدة البيانات: {mask_url(db_url)}")

    print("• فحص الاتصال ...")
    with engine.connect() as conn:
        version = conn.exec_driver_sql("SELECT version()").scalar()
        print(f"  ✓ متصل: {str(version)[:60]}...")

    print("• إنشاء الجداول (create_all) ...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.phone == ARGS.phone).one_or_none()
        if user is None:
            user = User(full_name=ARGS.full_name, phone=ARGS.phone,
                        email=ARGS.email.strip().lower(),
                        password_hash=hash_password(ARGS.password))
            db.add(user)
            db.flush()
            print(f"  ✓ أنشئ المستخدم: {ARGS.full_name} (دخول برقم/اسم: {ARGS.phone})")
        else:
            print(f"  ✓ المستخدم موجود بالفعل (id={user.id}) — لم يتغير شيء.")

        company = db.query(Company).filter(Company.name == ARGS.company).one_or_none()
        if company is None:
            company = Company(name=ARGS.company, business_type="عام", currency="EGP")
            db.add(company)
            db.flush()
            seed_chart_of_accounts(db, company.id)
            print(f"  ✓ أنشئت الشركة «{ARGS.company}» (id={company.id}) + دليل الحسابات الافتراضي.")
        else:
            print(f"  ✓ الشركة موجودة بالفعل (id={company.id}) — لم تتغير.")

        membership = (db.query(CompanyUser)
                      .filter(CompanyUser.company_id == company.id, CompanyUser.user_id == user.id)
                      .one_or_none())
        if membership is None:
            db.add(CompanyUser(company_id=company.id, user_id=user.id, role="owner"))
            print("  ✓ المستخدم أصبح مالكًا للشركة (role=owner).")
        else:
            print(f"  ✓ العضوية موجودة (role={membership.role}).")

        today = date.today()
        fy_start, fy_end = date(today.year, 1, 1), date(today.year, 12, 31)
        from app.models.operations import FinancialYear
        fy = (db.query(FinancialYear)
              .filter(FinancialYear.company_id == company.id, FinancialYear.start_date == fy_start)
              .one_or_none())
        if fy is None:
            db.add(FinancialYear(company_id=company.id, name=str(today.year),
                                 start_date=fy_start, end_date=fy_end, is_closed=False))
            print(f"  ✓ أنشئت السنة المالية {today.year} ({fy_start} ← {fy_end}).")
        else:
            print(f"  ✓ السنة المالية {fy.name} موجودة.")

        accounts_count = db.query(Account).filter(Account.company_id == company.id).count()
        db.commit()
        print(f"• حسابات دليل الحسابات للشركة: {accounts_count}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print()
    print("✓ القاعدة جاهزة. الخطوة الأخيرة على Render:")
    print("  hesabatak-backend → Environment → DATABASE_URL = نفس الرابط المستخدم هنا")
    print("  → Save Changes → Manual Deploy. الجداول موجودة فعلًا؛ السيرفر سيبدأ مباشرة.")
    print(f"  سجّل الدخول من التطبيق بـ: {ARGS.phone} / كلمة المرور المرسلة للسكربت.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
