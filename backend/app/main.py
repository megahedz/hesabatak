"""
حساباتك API — Phase 4: real authentication.

Every /companies/{company_id}/... route now requires a valid Bearer token
AND membership in that specific company (via verify_company_access) —
spec §44/§6. /auth/register and /auth/login are open; POST /companies
requires login (creates the company AND makes the caller its owner).
"""
import os
import re
from datetime import date, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Body, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.models.attachments import (
    Attachment, MAX_ATTACHMENT_BYTES, ALLOWED_CONTENT_TYPES,
)
from app.models.documents import SalesInvoice, PurchaseInvoice, Payment
from app.models.operations import (
    FinancialYear, FixedAsset, BankAccount, CashTransaction, BankTransaction,
)

from app.models.base import Base, engine, SessionLocal, IS_POSTGRES
from app.models import Company, Customer, Supplier, Product
from app.models.company import User, CompanyUser
from app.accounting.chart_of_accounts import seed_chart_of_accounts
from app.accounting.engine import AccountingService, AccountingError
from app.accounting.transactions import (
    record_sale, record_purchase, record_customer_payment,
    record_supplier_payment, record_expense,
)
from app.accounting.statements import customer_statement, supplier_statement
from app.accounting.reports import (
    trial_balance, profit_and_loss, balance_sheet, party_ledger_balance,
    general_ledger, cash_flow, vat_report,
)
from app.accounting.detailed_reports import (
    sales_report, purchases_report, inventory_report, expense_report,
    sales_by_item, purchases_by_item,
)
from app.accounting.dashboard_stats import monthly_sales_series, period_purchases
from app.accounting.exports import (
    build_pdf, build_xlsx, EXPORTS, ExportError,
)
from app.accounting.exports import _balance_sheet_spec, _profit_loss_spec
from app.accounting.backup import export_backup_file, restore_backup, RestoreError
from app.accounting.inventory import opening_stock_value
from app.models.accounts import SystemAccountCode
from app.auth.security import hash_password, verify_password, create_access_token, SECRET_KEY
from app.auth.dependencies import (
    get_db, get_current_user, verify_company_access, RoleChecker, ROLE_PERMISSIONS,
)
from fastapi import Response
from urllib.parse import quote

app = FastAPI(title="حساباتك API")

# كورس: تطبيق الويب (على نطاق مختلف) وأي عميل يستطيع استدعاء الـ API بحرية؛
# التوكن يبقى هو الحماية الحقيقية لكل نقطة نهاية.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """نقطة تهيئة خفيفة يستدعيها التطبيق فور فتحه لإيقاظ السيرفر النائم
    (Render free tier) قبل ما المستخدم يضغط تسجيل الدخول."""
    return {"status": "ok"}


@app.on_event("startup")
def on_startup():
    # ARCHITECTURE (mandatory): production must run on cloud PostgreSQL.
    # The Render deployment sets HESABATAK_REQUIRE_POSTGRES=1 — the server
    # then REFUSES to boot on SQLite, so the "ephemeral disk" failure mode
    # (all accounting data lost on every redeploy) can never happen again.
    if os.environ.get("HESABATAK_REQUIRE_POSTGRES") == "1" and not IS_POSTGRES:
        raise RuntimeError(
            "DATABASE_URL must point to a cloud PostgreSQL database in production "
            "(postgresql://...). SQLite is not allowed as the source of truth."
        )
    from sqlalchemy import text
    if IS_POSTGRES:
        # Fail fast with a clear message if the cloud DB is unreachable.
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            raise RuntimeError(f"Cannot reach the PostgreSQL database (DATABASE_URL): {e}")
    Base.metadata.create_all(bind=engine)
    # spec §78: never run with the placeholder secret except in explicit dev mode.
    if SECRET_KEY == "dev-only-insecure-key-change-me" and not os.environ.get("HESABATAK_ALLOW_DEV_SECRET"):
        raise RuntimeError(
            "HESABATAK_SECRET_KEY is not set. Set it to a real secret, or set "
            "HESABATAK_ALLOW_DEV_SECRET=1 to run with the insecure dev default (local testing only)."
        )


def _friendly_error(e: Exception, db: Session):
    db.rollback()
    if isinstance(e, AccountingError):
        raise HTTPException(400, str(e))
    raise HTTPException(400, "تعذر تنفيذ العملية. تأكد من صحة البيانات وحاول مرة أخرى.")


# ======================================================================
# AUTH — open routes, no token required to reach them.
# ======================================================================
auth_router = APIRouter(prefix="/auth", tags=["auth"])

# تحقق بسيط من صيغة البريد الإلكتروني: نص@نص.نطاق (بدون فراغات وبدون @ مزدوج).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@auth_router.post("/register")
def register(full_name: str, phone: str, email: str, password: str, db: Session = Depends(get_db)):
    # البريد الإجباري: يُطبَّع (أحرف صغيرة/بدون فراغات) ثم يُتحقق من صيغته.
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "البريد الإلكتروني غير صالح. مثال: name@example.com")
    # سياسة كلمة مرور أقوى: 8 أحرف على الأقل وتحتوي حرفًا ورقمًا.
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise HTTPException(400, "كلمة المرور يجب أن تكون 8 أحرف على الأقل وتحتوي على حرف ورقم واحد على الأقل.")
    existing = db.query(User).filter(User.phone == phone).one_or_none()
    if existing is not None:
        raise HTTPException(400, "رقم الهاتف مستخدم بالفعل.")
    if db.query(User).filter(User.email == email).one_or_none() is not None:
        raise HTTPException(400, "البريد الإلكتروني مستخدم بالفعل.")
    user = User(full_name=full_name, phone=phone, email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    token = create_access_token(user_id=user.id)
    return {"access_token": token, "token_type": "bearer", "user_id": user.id}


@auth_router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm's "username" field carries the phone number here.
    user = db.query(User).filter(User.phone == form_data.username).one_or_none()
    if user is None or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(401, "رقم الهاتف أو كلمة المرور غير صحيحة.")
    token = create_access_token(user_id=user.id)
    return {"access_token": token, "token_type": "bearer", "user_id": user.id}


@auth_router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "full_name": current_user.full_name, "phone": current_user.phone,
            "email": current_user.email}


# ======================================================================
# COMPANIES — creating a company requires login; listing "my companies" too.
# ======================================================================
companies_router = APIRouter(prefix="/companies", tags=["companies"])


@companies_router.post("")
def create_company(name: str, business_type: str = "عام", current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    company = Company(name=name, business_type=business_type, currency="EGP")
    db.add(company)
    db.flush()
    seed_chart_of_accounts(db, company.id)
    db.add(CompanyUser(company_id=company.id, user_id=current_user.id, role="owner"))
    _ensure_current_financial_year(db, company.id)
    db.commit()
    return {"id": company.id, "name": company.name}


def _fy_bounds(start_month: int, today: date) -> tuple[date, date]:
    """Fiscal-year bounds for the year that contains `today`, given the
    company's start month (e.g. start_month=1 → Jan 1..Dec 31)."""
    year = today.year
    start = date(year, start_month, 1)
    if start > today:
        start = date(year - 1, start_month, 1)
    end_year = start.year + 1
    end = date(end_year, start_month, 1) - timedelta(days=1)
    return start, end


def _ensure_current_financial_year(db: Session, company_id: int) -> FinancialYear:
    """Create the current fiscal year row if it doesn't exist (idempotent).
    Also used lazily by the /fiscal-years endpoint for companies created
    before this table existed."""
    company = db.query(Company).filter(Company.id == company_id).one()
    start, end = _fy_bounds(company.fiscal_year_start_month, date.today())
    fy = (db.query(FinancialYear)
          .filter(FinancialYear.company_id == company_id, FinancialYear.start_date == start)
          .one_or_none())
    if fy is None:
        fy = FinancialYear(company_id=company_id, name=str(start.year),
                           start_date=start, end_date=end)
        db.add(fy)
        db.flush()
    return fy


@companies_router.get("")
def list_my_companies(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    memberships = db.query(CompanyUser).filter(CompanyUser.user_id == current_user.id).all()
    companies = db.query(Company).filter(Company.id.in_([m.company_id for m in memberships])).all()
    return [{"id": c.id, "name": c.name} for c in companies]


# ======================================================================
# EVERYTHING BELOW is scoped to one company and requires BOTH a valid
# token AND membership in that company (verify_company_access checks
# both — see app/auth/dependencies.py).
# ======================================================================
scoped = APIRouter(prefix="/companies/{company_id}", dependencies=[Depends(verify_company_access)])


# ---------------------------------------------------------------- settings
@scoped.get("/settings")
def get_settings(company_id: int, db: Session = Depends(get_db)):
    """spec §57/§61: VAT / inventory / fiscal-year config drives what the UI shows."""
    company = db.query(Company).filter(Company.id == company_id).one_or_none()
    if company is None:
        raise HTTPException(404, "الشركة غير موجودة.")
    return {
        "id": company.id, "name": company.name, "business_type": company.business_type,
        "currency": company.currency, "fiscal_year_start_month": company.fiscal_year_start_month,
        "vat_enabled": bool(company.vat_enabled), "vat_rate": str(company.vat_rate),
        "inventory_enabled": bool(company.inventory_enabled),
        "catalog_mode": bool(company.catalog_mode),
    }


@scoped.post("/settings")
def update_settings(
    company_id: int,
    vat_enabled: Optional[bool] = None,
    vat_rate: Optional[Decimal] = None,
    inventory_enabled: Optional[bool] = None,
    catalog_mode: Optional[bool] = None,
    fiscal_year_start_month: Optional[int] = None,
    name: Optional[str] = None,
    business_type: Optional[str] = None,
    membership: CompanyUser = Depends(RoleChecker("manage_settings")),
    db: Session = Depends(get_db)):
    """Partial update — only the fields the caller sends change."""
    company = db.query(Company).filter(Company.id == company_id).one_or_none()
    if company is None:
        raise HTTPException(404, "الشركة غير موجودة.")
    if name is not None and name.strip():
        company.name = name.strip()
    if business_type is not None:
        company.business_type = business_type
    if fiscal_year_start_month is not None:
        if not 1 <= fiscal_year_start_month <= 12:
            raise HTTPException(400, "شهر بداية السنة المالية يجب أن يكون بين 1 و 12.")
        company.fiscal_year_start_month = fiscal_year_start_month
    if vat_rate is not None:
        if not (Decimal("0") <= vat_rate <= Decimal("100")):
            raise HTTPException(400, "نسبة ضريبة القيمة المضافة يجب أن تكون بين 0 و 100.")
        company.vat_rate = vat_rate
    if vat_enabled is not None:
        company.vat_enabled = vat_enabled
    if inventory_enabled is not None:
        company.inventory_enabled = inventory_enabled
    if catalog_mode is not None:
        # «وضع الأصناف»: تعريف الأصناف بدون جرد — تفعيله يطفئ الجرد تلقائيًا.
        company.catalog_mode = catalog_mode
        if catalog_mode:
            company.inventory_enabled = False
    db.commit()
    return get_settings(company_id, db)


# ---------------------------------------------------------------- products
@scoped.get("/products")
def list_products(company_id: int, db: Session = Depends(get_db)):
    products = db.query(Product).filter(Product.company_id == company_id,
                                        Product.deleted_at.is_(None)).all()
    return [{
        "id": p.id, "name": p.name, "sku": p.sku, "barcode": p.barcode,
        "unit": p.unit, "description": p.description,
        "purchase_price": str(p.purchase_price),
        "selling_price": str(p.selling_price), "current_stock": str(p.current_stock),
        "minimum_stock": str(p.minimum_stock),
    } for p in products]


@scoped.post("/products")
def create_product(
    company_id: int, name: str, sku: Optional[str] = None,
    barcode: Optional[str] = None, unit: str = "قطعة",
    description: Optional[str] = None,
    purchase_price: Decimal = Decimal("0"), selling_price: Decimal = Decimal("0"),
    opening_stock_qty: Decimal = Decimal("0"),
    minimum_stock: Decimal = Decimal("0"),
    record: CompanyUser = Depends(RoleChecker("record")),
    db: Session = Depends(get_db)):
    """
    Create a product. If it starts with stock already on hand, the stock is
    received at `purchase_price` and its value is posted as
    Inventory Dr / Owner Capital Cr (owner contribution, spec §71 assumption)
    — one DB transaction for product + movement + journal entry.
    In catalog_mode, opening_stock_qty is ignored (definition-only catalog).
    """
    if not name.strip():
        raise HTTPException(400, "اسم المنتج مطلوب.")
    if purchase_price < 0 or selling_price < 0 or opening_stock_qty < 0:
        raise HTTPException(400, "الأسعار والكميات لا يمكن أن تكون سالبة.")

    company = db.query(Company).filter(Company.id == company_id).one()
    product = Product(
        company_id=company_id, name=name.strip(), sku=sku, barcode=barcode,
        unit=unit, description=description,
        purchase_price=purchase_price, selling_price=selling_price,
        minimum_stock=minimum_stock, current_stock=0,
    )
    db.add(product)
    db.flush()

    # catalog_mode: تعريف فقط — لا مخزون افتتاحي ولا قيد مساهمة رأس مال.
    if opening_stock_qty > 0 and not company.catalog_mode:
        if purchase_price <= 0:
            raise HTTPException(400, "لا يمكن إضافة مخزون افتتاحي بدون تكلفة شراء صحيحة.")
        opening_stock_value(
            db, company_id=company_id, entry_date=date.today(), product=product,
            quantity=opening_stock_qty, unit_cost=purchase_price,
        )
        AccountingService.create_opening_stock(
            db, company_id=company_id, entry_date=date.today(),
            amount=opening_stock_qty * purchase_price,
            description=f"مخزون افتتاحي - {product.name}",
        )
    db.commit()
    return {"id": product.id, "name": product.name}


@scoped.get("/dashboard")
def dashboard(company_id: int, start: Optional[date] = None, db: Session = Depends(get_db)):
    """Dashboard cards for the period starting at `start` (default: this month)."""
    today = date.today()
    month_start = start or today.replace(day=1)
    cash = party_ledger_balance(db, company_id, SystemAccountCode.CASH.value)
    bank = party_ledger_balance(db, company_id, SystemAccountCode.BANK.value)
    receivable = party_ledger_balance(db, company_id, SystemAccountCode.ACCOUNTS_RECEIVABLE.value)
    payable = party_ledger_balance(db, company_id, SystemAccountCode.ACCOUNTS_PAYABLE.value)
    pl_period = profit_and_loss(db, company_id, start=month_start, end=today)
    return {
        "رصيد_الخزينة": str(cash), "رصيد_البنك": str(bank),
        "لدى_العملاء": str(receivable), "للموردين": str(payable),
        "مبيعات_الفترة": str(pl_period["revenue"]), "المشتريات": str(period_purchases(db, company_id, month_start)),
        "المصروفات": str(pl_period["operating_expenses"]), "صافي_الربح": str(pl_period["net_profit"]),
        "العملة": "ج.م",
        "مبيعات_آخر_6أشهر": monthly_sales_series(db, company_id, months=6),
    }


# ---------------------------------------------------------------- customers
@scoped.post("/customers")
def create_customer(
    company_id: int, name: str, phone: Optional[str] = None,
    opening_balance: Decimal = Decimal("0"),
    record: CompanyUser = Depends(RoleChecker("record")),
    db: Session = Depends(get_db)):
    customer = Customer(company_id=company_id, name=name, phone=phone, opening_balance=opening_balance)
    db.add(customer)
    db.commit()
    return {"id": customer.id, "name": customer.name}


@scoped.get("/customers")
def list_customers(company_id: int, db: Session = Depends(get_db)):
    customers = db.query(Customer).filter(Customer.company_id == company_id).all()
    return [{"id": c.id, "name": c.name, "phone": c.phone} for c in customers]


@scoped.get("/customers/balances")
def customer_balances(company_id: int, db: Session = Depends(get_db)):
    """Ledger balance per customer (AR lines linked to each customer) — what
    the customers screen shows against every name. Unpaid opening balances
    count too (the AR account itself starts from them)."""
    from app.models.journal import JournalEntryLine, JournalEntry
    from app.models.accounts import Account
    from app.models.parties import Customer as CustomerModel
    rows = (
        db.query(
            JournalEntryLine.customer_id,
            func.coalesce(func.sum(JournalEntryLine.debit) - func.sum(JournalEntryLine.credit), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .filter(
            JournalEntry.company_id == company_id,
            JournalEntryLine.customer_id.isnot(None),
            Account.code == SystemAccountCode.ACCOUNTS_RECEIVABLE.value,
        )
        .group_by(JournalEntryLine.customer_id)
        .all()
    )
    balances = {cid: Decimal(str(net)) for cid, net in rows}
    for c in db.query(CustomerModel).filter(CustomerModel.company_id == company_id).all():
        balances.setdefault(c.id, Decimal("0"))
    return {str(cid): float(v) for cid, v in sorted(balances.items())}


@scoped.get("/suppliers/balances")
def supplier_balances(company_id: int, db: Session = Depends(get_db)):
    """Ledger balance per supplier (credit minus debit on AP lines) — positive
    means we still owe them."""
    from app.models.journal import JournalEntryLine, JournalEntry
    from app.models.accounts import Account
    from app.models.parties import Supplier as SupplierModel
    rows = (
        db.query(
            JournalEntryLine.supplier_id,
            func.coalesce(func.sum(JournalEntryLine.credit) - func.sum(JournalEntryLine.debit), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .filter(
            JournalEntry.company_id == company_id,
            JournalEntryLine.supplier_id.isnot(None),
            Account.code == SystemAccountCode.ACCOUNTS_PAYABLE.value,
        )
        .group_by(JournalEntryLine.supplier_id)
        .all()
    )
    balances = {sid: Decimal(str(net)) for sid, net in rows}
    for s in db.query(SupplierModel).filter(SupplierModel.company_id == company_id).all():
        balances.setdefault(s.id, Decimal("0"))
    return {str(sid): float(v) for sid, v in sorted(balances.items())}


@scoped.get("/customers/{customer_id}/statement")
def get_customer_statement(company_id: int, customer_id: int, db: Session = Depends(get_db)):
    s = customer_statement(db, company_id, customer_id)
    return {
        "اسم_العميل": s["customer_name"], "الرصيد_الافتتاحي": str(s["opening_balance"]),
        "الرصيد_الختامي": str(s["closing_balance"]),
        "الحركات": [{"التاريخ": str(l.line_date), "البيان": l.description,
                      "مدين": str(l.debit), "دائن": str(l.credit), "الرصيد": str(l.running_balance)}
                     for l in s["lines"]],
    }


# ---------------------------------------------------------------- suppliers
@scoped.post("/suppliers")
def create_supplier(
    company_id: int, name: str, phone: Optional[str] = None,
    opening_balance: Decimal = Decimal("0"),
    record: CompanyUser = Depends(RoleChecker("record")),
    db: Session = Depends(get_db)):
    supplier = Supplier(company_id=company_id, name=name, phone=phone, opening_balance=opening_balance)
    db.add(supplier)
    db.commit()
    return {"id": supplier.id, "name": supplier.name}


@scoped.get("/suppliers")
def list_suppliers(company_id: int, db: Session = Depends(get_db)):
    suppliers = db.query(Supplier).filter(Supplier.company_id == company_id).all()
    return [{"id": s.id, "name": s.name, "phone": s.phone} for s in suppliers]


@scoped.get("/suppliers/{supplier_id}/statement")
def get_supplier_statement(company_id: int, supplier_id: int, db: Session = Depends(get_db)):
    s = supplier_statement(db, company_id, supplier_id)
    return {
        "اسم_المورد": s["supplier_name"], "الرصيد_الافتتاحي": str(s["opening_balance"]),
        "الرصيد_الختامي": str(s["closing_balance"]),
        "الحركات": [{"التاريخ": str(l.line_date), "البيان": l.description,
                      "مدين": str(l.debit), "دائن": str(l.credit), "الرصيد": str(l.running_balance)}
                     for l in s["lines"]],
    }


# ---------------------------------------------------------------- operations
ATTACHMENT_OWNER_KINDS = {
    "customer": "customer_id",
    "supplier": "supplier_id",
    "sale": "sales_invoice_id",
    "purchase": "purchase_invoice_id",
    "payment": "payment_id",
}


def _attachment_owner_id(company_id: int, owner_kind: str, owner_id: int, db: Session):
    """Resolve + validate the attachment's owner row (company-scoped)."""
    column = ATTACHMENT_OWNER_KINDS.get(owner_kind)
    if column is None:
        raise HTTPException(400, "نوع المرفق يجب أن يكون: customer أو supplier أو sale أو purchase أو payment.")
    model = {
        "customer": Customer, "supplier": Supplier,
        "sale": SalesInvoice, "purchase": PurchaseInvoice, "payment": Payment,
    }[owner_kind]
    row = db.query(model).filter(model.id == owner_id, model.company_id == company_id).one_or_none()
    if row is None:
        raise HTTPException(404, "المستند المرفق إليه غير موجود في هذه الشركة.")
    return column, owner_id


@scoped.post("/attachments/{owner_kind}/{owner_id}")
async def upload_attachment(
    company_id: int, owner_kind: str, owner_id: int,
    file: UploadFile = File(...),
    record: CompanyUser = Depends(RoleChecker("record")),
    db: Session = Depends(get_db)):
    """رفع مرفق (صورة أو PDF) على عميل/مورد/فاتورة/دفعة.
    الملف يُخزَّن داخل قاعدة البيانات نفسها (BLOB) لأن قرص Render المجاني مؤقت."""
    column, resolved_id = _attachment_owner_id(company_id, owner_kind, owner_id, db)
    content = await file.read()
    if not content:
        raise HTTPException(400, "الملف فارغ.")
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(400, "حجم الملف يتجاوز الحد المسموح (2.5 ميغابايت).")
    ctype = (file.content_type or "").lower().split(";")[0].strip()
    if ctype not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(400, "يُسمح فقط بالصور (JPG/PNG/WEBP/GIF/HEIC) وملفات PDF.")
    att = Attachment(
        company_id=company_id,
        **{column: resolved_id},
        file_name=(file.filename or "attachment").strip()[:255] or "attachment",
        content_type=ctype,
        size_bytes=len(content),
        data=content,
    )
    db.add(att)
    db.commit()
    return {"id": att.id, "file_name": att.file_name, "content_type": att.content_type,
            "size_bytes": att.size_bytes}


@scoped.get("/attachments/{owner_kind}/{owner_id}")
def list_attachments(company_id: int, owner_kind: str, owner_id: int,
                     db: Session = Depends(get_db)):
    """قائمة مرفقات مستند معين (بدون محتوى الملف)."""
    column, _ = _attachment_owner_id(company_id, owner_kind, owner_id, db)
    rows = (db.query(Attachment)
            .filter(Attachment.company_id == company_id, getattr(Attachment, column) == owner_id)
            .order_by(Attachment.id.asc()).all())
    return [{"id": a.id, "file_name": a.file_name, "content_type": a.content_type,
             "size_bytes": a.size_bytes} for a in rows]


@scoped.get("/attachments/{owner_kind}/{owner_id}/{attachment_id}")
def download_attachment(company_id: int, owner_kind: str, owner_id: int, attachment_id: int,
                        db: Session = Depends(get_db)):
    """تنزيل محتوى المرفق (الملف الأصلي كما رُفع)."""
    column, _ = _attachment_owner_id(company_id, owner_kind, owner_id, db)
    att = (db.query(Attachment)
           .filter(Attachment.company_id == company_id,
                   getattr(Attachment, column) == owner_id,
                   Attachment.id == attachment_id)
           .one_or_none())
    if att is None:
        raise HTTPException(404, "المرفق غير موجود.")
    from urllib.parse import quote
    ascii_name = f"attachment-{att.id}.bin"
    arabic_name = quote(att.file_name)
    return Response(content=att.data, media_type=att.content_type, headers={
        "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{arabic_name}",
    })


@scoped.delete("/attachments/{owner_kind}/{owner_id}/{attachment_id}")
def delete_attachment(company_id: int, owner_kind: str, owner_id: int, attachment_id: int,
                      record: CompanyUser = Depends(RoleChecker("record")),
                      db: Session = Depends(get_db)):
    """حذف مرفق (صلاحية تسجيل العمليات)."""
    column, _ = _attachment_owner_id(company_id, owner_kind, owner_id, db)
    att = (db.query(Attachment)
           .filter(Attachment.company_id == company_id,
                   getattr(Attachment, column) == owner_id,
                   Attachment.id == attachment_id)
           .one_or_none())
    if att is None:
        raise HTTPException(404, "المرفق غير موجود.")
    db.delete(att)
    db.commit()
    return {"status": "ok"}


@scoped.post("/operations/sale")
def op_sale(
    company_id: int, amount: Decimal, is_credit: bool = False, method: str = "cash",
    customer_id: Optional[int] = None, vat_amount: Decimal = Decimal("0"),
    product_id: Optional[int] = None, quantity: Decimal = Decimal("0"),
    unit_price: Optional[Decimal] = None,
    items_json: Optional[str] = None,
    record: CompanyUser = Depends(RoleChecker("record")),
    db: Session = Depends(get_db)):
    """One sale. When product_id+quantity are given, the invoice records the
    line, stock is consumed at weighted-average cost, and the computed COGS is
    posted automatically — the caller never sends COGS (spec §9: engine only).
    Multi-line clients (the redesigned invoice screen) send `items_json`:
    [{"product_id", "quantity", "unit_price"}] — `amount` must equal the
    items' line_total sum, which the UI computes and shows."""
    try:
        items = None
        if items_json:
            items = _parse_items_json(items_json)
        elif product_id is not None:
            if quantity <= 0:
                raise AccountingError("كمية البيع يجب أن تكون أكبر من صفر.")
            item = {"product_id": product_id, "quantity": quantity}
            if unit_price is not None:
                item["unit_price"] = unit_price
            items = [item]
        invoice = record_sale(db, company_id=company_id, entry_date=date.today(), amount=amount,
                               is_credit=is_credit, method=method, customer_id=customer_id,
                               vat_amount=vat_amount, items=items)
        db.commit()
        return {"invoice_number": invoice.invoice_number, "invoice_id": invoice.id, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


def _parse_items_json(raw: str) -> list[dict]:
    """Parse the mobile client's items payload. Values arrive as strings via
    query params; numbers are coerced so record_sale can validate them.
    Each row is either a catalog line {"product_id", "quantity", "unit_price",
    "description"?} or a free-text service line {"name", "quantity",
    "unit_price"} without a product_id (مكتب يبيع خدمات بدون أصناف معرّفة)."""
    import json
    try:
        rows = json.loads(raw)
        assert isinstance(rows, list) and rows
    except Exception:
        raise AccountingError("بنود الفاتورة غير صالحة.")
    parsed = []
    for r in rows:
        try:
            raw_pid = r.get("product_id")
            name = str(r.get("name") or "").strip()
            desc = str(r.get("description") or "").strip()
            row: dict = {
                "quantity": Decimal(str(r["quantity"])),
                "unit_price": Decimal(str(r["unit_price"])),
            }
            if raw_pid is not None and str(raw_pid).strip() not in ("", "None", "null"):
                row["product_id"] = int(raw_pid)
                if desc:
                    row["description"] = desc[:200]
            else:
                # service line: the free text IS the line (fallback to description)
                label = name or desc
                if not label:
                    raise AccountingError("بند بدون صنف يحتاج وصفًا مكتوبًا.")
                row["description"] = label[:200]
            parsed.append(row)
        except AccountingError:
            raise
        except Exception:
            raise AccountingError("بنود الفاتورة غير صالحة.")
    return parsed


@scoped.post("/operations/purchase")
def op_purchase(
    company_id: int, amount: Decimal, is_credit: bool = False, method: str = "cash",
    supplier_id: Optional[int] = None, goes_to_inventory: bool = False,
    vat_amount: Decimal = Decimal("0"),
    product_id: Optional[int] = None, quantity: Decimal = Decimal("0"),
    items_json: Optional[str] = None,
    record: CompanyUser = Depends(RoleChecker("record")),
    db: Session = Depends(get_db)):
    """One purchase. With product_id+quantity, stock is received at
    amount/quantity as unit cost and the weighted average is re-computed.
    Multi-line clients (the redesigned invoice screen) send `items_json` —
    same shape as the sale endpoint; items force the purchase into inventory
    and must sum to `amount` (per-line discounts are already baked into the
    unit prices the client sends)."""
    try:
        items = None
        if items_json:
            goes_to_inventory = True  # named products physically arrive
            items = _parse_items_json(items_json)
        elif product_id is not None:
            if quantity <= 0:
                raise AccountingError("كمية الشراء يجب أن تكون أكبر من صفر.")
            goes_to_inventory = True  # a named product physically arrives → inventory
            items = [{"product_id": product_id, "quantity": quantity,
                      "unit_price": (amount / quantity).quantize(Decimal("0.01"))}]
        invoice = record_purchase(db, company_id=company_id, entry_date=date.today(), amount=amount,
                                   is_credit=is_credit, method=method, supplier_id=supplier_id,
                                   vat_amount=vat_amount, goes_to_inventory=goes_to_inventory,
                                   items=items)
        db.commit()
        return {"invoice_number": invoice.invoice_number, "invoice_id": invoice.id, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


@scoped.post("/operations/customer-payment")
def op_customer_payment(
    company_id: int, amount: Decimal, customer_id: int, method: str = "cash",
    record: CompanyUser = Depends(RoleChecker("record")),
    db: Session = Depends(get_db)):
    try:
        payment = record_customer_payment(db, company_id=company_id, entry_date=date.today(),
                                           amount=amount, customer_id=customer_id, method=method)
        db.commit()
        return {"payment_id": payment.id, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


@scoped.post("/operations/supplier-payment")
def op_supplier_payment(
    company_id: int, amount: Decimal, supplier_id: int, method: str = "cash",
    record: CompanyUser = Depends(RoleChecker("record")),
    db: Session = Depends(get_db)):
    try:
        payment = record_supplier_payment(db, company_id=company_id, entry_date=date.today(),
                                           amount=amount, supplier_id=supplier_id, method=method)
        db.commit()
        return {"payment_id": payment.id, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


@scoped.post("/operations/expense")
def op_expense(
    company_id: int, amount: Decimal, method: str = "cash",
    expense_account_code: str = SystemAccountCode.UNCATEGORIZED_EXPENSE.value,
    notes: Optional[str] = None,
    custom_label: Optional[str] = None,
    record: CompanyUser = Depends(RoleChecker("record")),
    db: Session = Depends(get_db)):
    """مصروف: إما على حساب جاهز من دليل الحسابات (كهرباء/مياه/مرتبات…)
    أو «مصروف مخصص» — يُنشئ حساب 6xxx جديد باسم حر يكتبه المستخدم (مرة واحدة،
    ثم يظهر في دليل الحسابات والتقارير كحساب دائم)."""
    try:
        if custom_label and custom_label.strip():
            expense_account_code = _get_or_create_expense_account(
                db, company_id, custom_label.strip())
        expense = record_expense(db, company_id=company_id, entry_date=date.today(), amount=amount,
                                  expense_account_code=expense_account_code, method=method, notes=notes)
        db.commit()
        return {"expense_id": expense.id, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


def _get_or_create_expense_account(db: Session, company_id: int, label: str) -> str:
    """ابحث عن حساب مصروف 6xxx بهذا الاسم، أو أنشئه بأول كود متاح 6701..6899.
    لا يسمح بتكرار الاسم لنفس الشركة — الحساب دائم ويظهر في التقارير."""
    from app.models.accounts import Account, AccountType
    existing = (db.query(Account)
                .filter(Account.company_id == company_id,
                        Account.name_ar == label,
                        Account.code.like("6%"))
                .one_or_none())
    if existing is not None:
        return existing.code
    exp_type = db.query(AccountType).filter(AccountType.code == "EXPENSE").one()
    taken = {a.code for a in db.query(Account).filter(
        Account.company_id == company_id, Account.code.like("6%")).all()}
    for n in range(6701, 6900):
        code = str(n)
        if code not in taken:
            account = Account(company_id=company_id, code=code, name_ar=label,
                              name_en=label, account_type_id=exp_type.id, is_system=False)
            db.add(account)
            db.flush()
            return code
    raise AccountingError("لا توجد أكواد متاحة لمصروف مخصص جديد.")


@scoped.post("/operations/capital")
def op_capital(
    company_id: int, amount: Decimal, method: str = "cash",
    record: CompanyUser = Depends(RoleChecker("record")),
    db: Session = Depends(get_db)):
    try:
        entry = AccountingService.create_capital(db, company_id=company_id, entry_date=date.today(),
                                                   amount=amount, method=method)
        db.commit()
        return {"journal_entry_id": entry.id, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


@scoped.post("/operations/owner-withdrawal")
def op_owner_withdrawal(
    company_id: int, amount: Decimal, method: str = "cash",
    record: CompanyUser = Depends(RoleChecker("record")),
    db: Session = Depends(get_db)):
    try:
        entry = AccountingService.create_owner_withdrawal(db, company_id=company_id, entry_date=date.today(),
                                                            amount=amount, method=method)
        db.commit()
        return {"journal_entry_id": entry.id, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


@scoped.post("/operations/transfer")
def op_transfer(
    company_id: int, amount: Decimal, from_code: str, to_code: str,
    record: CompanyUser = Depends(RoleChecker("record")),
    db: Session = Depends(get_db)):
    try:
        entry = AccountingService.create_transfer(db, company_id=company_id, entry_date=date.today(),
                                                    amount=amount, from_code=from_code, to_code=to_code)
        db.commit()
        return {"journal_entry_id": entry.id, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


# ---------------------------------------------------------------- reports
@scoped.get("/reports/trial-balance")
def report_trial_balance(company_id: int, db: Session = Depends(get_db)):
    tb = trial_balance(db, company_id)
    return {
        "is_balanced": tb["is_balanced"], "total_debit": str(tb["total_debit"]), "total_credit": str(tb["total_credit"]),
        "rows": [{"code": r.code, "name_ar": r.name_ar, "debit": str(r.total_debit),
                  "credit": str(r.total_credit), "balance": str(r.balance)} for r in tb["rows"]],
    }


@scoped.get("/reports/balance-sheet")
def report_balance_sheet(company_id: int, db: Session = Depends(get_db)):
    bs = balance_sheet(db, company_id)
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in bs.items()}


@scoped.get("/reports/profit-and-loss")
def report_profit_and_loss(company_id: int, db: Session = Depends(get_db)):
    pl = profit_and_loss(db, company_id)
    return {k: str(v) for k, v in pl.items()}


@scoped.get("/reports/general-ledger")
def report_general_ledger(company_id: int, account_code: str,
                           start: Optional[date] = None, end: Optional[date] = None,
                           db: Session = Depends(get_db)):
    """spec §22: دفتر الأستاذ لحساب واحد، من القيود مباشرة مع رصيد متحرك."""
    try:
        gl = general_ledger(db, company_id, account_code, start=start, end=end)
    except ValueError:
        raise HTTPException(404, "الحساب غير موجود.")
    return {
        "account_code": gl["account_code"], "account_name": gl["account_name"],
        "opening_balance": str(gl["opening_balance"]), "closing_balance": str(gl["closing_balance"]),
        "total_debit": str(gl["total_debit"]), "total_credit": str(gl["total_credit"]),
        "lines": [{"date": str(l.entry_date), "description": l.description,
                   "reference_type": l.reference_type, "debit": str(l.debit),
                   "credit": str(l.credit), "balance": str(l.running_balance)}
                  for l in gl["lines"]],
    }


@scoped.get("/reports/cash-flow")
def report_cash_flow(company_id: int, start: Optional[date] = None, end: Optional[date] = None,
                     db: Session = Depends(get_db)):
    """حركة النقدية (الخزينة + البنك) لفترة محددة، من القيود مباشرة."""
    cf = cash_flow(db, company_id, start=start, end=end)
    return {
        "opening": str(cf["opening"]), "inflow": str(cf["inflow"]),
        "outflow": str(cf["outflow"]), "net": str(cf["net"]), "closing": str(cf["closing"]),
        "by_reference": [{"reference_type": r["reference_type"], "inflow": str(r["inflow"]),
                          "outflow": str(r["outflow"])} for r in cf["by_reference"]],
    }


@scoped.get("/reports/vat")
def report_vat(company_id: int, start: Optional[date] = None, end: Optional[date] = None,
               db: Session = Depends(get_db)):
    """spec §33: المحصّل - المدفوع = الصافي المستحق، من حسابات VAT في القيود."""
    vat = vat_report(db, company_id, start=start, end=end)
    return {k: str(v) for k, v in vat.items()}


# ---------------------------------------------------------------- detailed reports (Phase 6)
@scoped.get("/reports/sales")
def report_sales(company_id: int, start: Optional[date] = None, end: Optional[date] = None,
                 period: Optional[str] = None, by_item: bool = False,
                 db: Session = Depends(get_db)):
    """تقرير المبيعات التفصيلي. فترات سريعة period=today|month|year،
    و by_item=true يعيد التقرير مجمّعًا على أساس الصنف (بالعدد والكمية والقيمة)."""
    start, end = _period_bounds(period, start, end)
    if by_item:
        rep = sales_by_item(db, company_id, start, end)
        return {"rows": rep["rows"], "totals": {"total": str(rep["total"])},
                "period": period, "start": str(start) if start else None,
                "end": str(end) if end else None}
    rep = sales_report(db, company_id, start, end)
    return {
        "rows": [{"invoice_number": r.invoice_number, "invoice_date": str(r.invoice_date),
                  "customer_name": r.customer_name, "is_credit": r.is_credit,
                  "payment_method": r.payment_method, "subtotal": str(r.subtotal),
                  "vat_amount": str(r.vat_amount), "total": str(r.total)} for r in rep["rows"]],
        "lines": {inv: [{"product_name": l.product_name, "quantity": str(l.quantity),
                         "unit_price": str(l.unit_price), "line_total": str(l.line_total)}
                        for l in lines]
                  for inv, lines in rep["lines"].items()},
        "totals": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in rep["totals"].items()},
    }


@scoped.get("/reports/purchases")
def report_purchases(company_id: int, start: Optional[date] = None, end: Optional[date] = None,
                     period: Optional[str] = None, by_item: bool = False,
                     db: Session = Depends(get_db)):
    """تقرير المشتريات التفصيلي. فترات سريعة period=today|month|year،
    و by_item=true يعيد التقرير مجمّعًا على أساس الصنف."""
    start, end = _period_bounds(period, start, end)
    if by_item:
        rep = purchases_by_item(db, company_id, start, end)
        return {"rows": rep["rows"], "totals": {"total": str(rep["total"])},
                "period": period, "start": str(start) if start else None,
                "end": str(end) if end else None}
    rep = purchases_report(db, company_id, start, end)
    return {
        "rows": [{"invoice_number": r.invoice_number, "invoice_date": str(r.invoice_date),
                  "supplier_name": r.supplier_name, "is_credit": r.is_credit,
                  "payment_method": r.payment_method, "subtotal": str(r.subtotal),
                  "vat_amount": str(r.vat_amount), "total": str(r.total)} for r in rep["rows"]],
        "lines": {inv: [{"product_name": l.product_name, "quantity": str(l.quantity),
                         "unit_price": str(l.unit_price), "line_total": str(l.line_total)}
                        for l in lines]
                  for inv, lines in rep["lines"].items()},
        "totals": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in rep["totals"].items()},
    }


def _period_bounds(period: Optional[str], start: Optional[date],
                   end: Optional[date]) -> tuple[Optional[date], Optional[date]]:
    """فترات التقارير السريعة من التطبيق: today / month / year —
    التواريخ الصريحة تتفوق دائمًا عند ورودها معًا."""
    if start is not None and end is not None:
        return start, end
    today = date.today()
    if period == "today":
        return today, today
    if period == "month":
        return today.replace(day=1), today
    if period == "year":
        return today.replace(month=1, day=1), today
    return start, end


@scoped.get("/reports/inventory")
def report_inventory(company_id: int, db: Session = Depends(get_db)):
    """تقرير المخزون: الكميات والقيمة بتكلفة المتوسط المرجح + القيمة البيعية (بند 39)."""
    rep = inventory_report(db, company_id)
    return {
        "rows": [{"product_id": r.product_id, "name": r.name, "sku": r.sku, "unit": r.unit,
                  "current_stock": str(r.current_stock), "avg_cost": str(r.avg_cost),
                  "selling_price": str(r.selling_price), "stock_value": str(r.stock_value),
                  "retail_value": str(r.retail_value), "minimum_stock": str(r.minimum_stock),
                  "is_low": r.is_low, "is_out": r.is_out} for r in rep["rows"]],
        "totals": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in rep["totals"].items()},
    }


@scoped.get("/reports/expenses")
def report_expenses(company_id: int, start: Optional[date] = None, end: Optional[date] = None,
                    period: Optional[str] = None,
                    db: Session = Depends(get_db)):
    """تقرير المصروفات مجمّعة على حسابات المصروفات (بنود المصروف) —
    مع فترات سريعة period=today|month|year."""
    start, end = _period_bounds(period, start, end)
    rep = expense_report(db, company_id, start, end)
    return {"rows": [{"code": r["code"], "name_ar": r["name_ar"], "amount": str(r["amount"])}
                     for r in rep["rows"]],
            "total": str(rep["total"])}


# ---------------------------------------------------------------- fiscal years (spec: financial_years)
@scoped.get("/fiscal-years")
def list_fiscal_years(company_id: int, db: Session = Depends(get_db)):
    """قائمة السنوات المالية — تُنشأ السنة الحالية تلقائيًا إن لم توجد (idempotent)."""
    _ensure_current_financial_year(db, company_id)
    db.commit()
    rows = (db.query(FinancialYear).filter(FinancialYear.company_id == company_id)
            .order_by(FinancialYear.start_date.desc()).all())
    return [{"id": f.id, "name": f.name, "start_date": str(f.start_date),
             "end_date": str(f.end_date), "is_closed": bool(f.is_closed)} for f in rows]


# ---------------------------------------------------------------- fixed assets (spec: fixed_assets)
@scoped.get("/assets")
def list_fixed_assets(company_id: int, db: Session = Depends(get_db)):
    """سجل الأصول الثابتة المسجلة (جدول حقيقي) — الحركة المحاسبية نفسها في القيود."""
    rows = (db.query(FixedAsset).filter(FixedAsset.company_id == company_id,
                                        FixedAsset.deleted_at.is_(None))
            .order_by(FixedAsset.acquisition_date.desc(), FixedAsset.id.desc()).all())
    return [{"id": a.id, "name": a.name, "notes": a.notes,
             "acquisition_date": str(a.acquisition_date), "cost": str(a.cost),
             "from_code": a.from_code, "journal_entry_id": a.journal_entry_id} for a in rows]


@scoped.post("/assets")
def create_fixed_asset(
    company_id: int, name: str, cost: Decimal, from_code: str = "1100",
    notes: Optional[str] = None,
    record: CompanyUser = Depends(RoleChecker("record")),
    db: Session = Depends(get_db)):
    """تسجيل أصل ثابت: جدول fixed_assets + قيد حقيقي (الأصل مدين / الخزينة أو البنك دائن)
    في نفس المعاملة — الأصل يظهر فورًا في دفتر الأستاذ وكشف حركاته."""
    from_code = from_code.strip()
    if from_code not in (SystemAccountCode.CASH.value, SystemAccountCode.BANK.value):
        raise HTTPException(400, "يجب سحب تكلفة الأصل من الخزينة (1100) أو البنك (1200) فقط.")
    if not name.strip():
        raise HTTPException(400, "اسم الأصل مطلوب.")
    if cost <= 0:
        raise HTTPException(400, "تكلفة الأصل يجب أن تكون أكبر من صفر.")
    try:
        entry = AccountingService.create_transfer(
            db, company_id=company_id, entry_date=date.today(), amount=cost,
            from_code=from_code, to_code="1500",
            description=f"شراء أصل ثابت: {name.strip()}",
        )
        asset = FixedAsset(
            company_id=company_id, name=name.strip(), notes=notes,
            acquisition_date=date.today(), cost=cost, from_code=from_code,
            journal_entry_id=entry.id,
        )
        db.add(asset)
        db.commit()
        return {"id": asset.id, "name": asset.name, "journal_entry_id": entry.id}
    except Exception as e:
        _friendly_error(e, db)


# ---------------------------------------------------------------- bank accounts (spec: bank_accounts)
@scoped.get("/bank-accounts")
def list_bank_accounts(company_id: int, db: Session = Depends(get_db)):
    """البنوك المسجلة للشركة (حساب 1200 في الدليل يبقى مصدر الرصيد المحاسبي)."""
    rows = (db.query(BankAccount).filter(BankAccount.company_id == company_id,
                                         BankAccount.deleted_at.is_(None))
            .order_by(BankAccount.id.asc()).all())
    return [{"id": b.id, "name": b.name, "account_number": b.account_number,
             "notes": b.notes} for b in rows]


@scoped.post("/bank-accounts")
def create_bank_account(
    company_id: int, name: str, account_number: Optional[str] = None,
    notes: Optional[str] = None,
    record: CompanyUser = Depends(RoleChecker("record")),
    db: Session = Depends(get_db)):
    if not name.strip():
        raise HTTPException(400, "اسم البنك مطلوب.")
    bank = BankAccount(company_id=company_id, name=name.strip(),
                       account_number=(account_number or None), notes=notes)
    db.add(bank)
    db.commit()
    return {"id": bank.id, "name": bank.name}


# ---------------------------------------------------------------- cash / bank transaction ledgers (spec)
@scoped.get("/cash-transactions")
def list_cash_transactions(company_id: int, start: Optional[date] = None,
                           end: Optional[date] = None, db: Session = Depends(get_db)):
    """كشف حركات الخزينة (1100) من جدول cash_transactions — يُبنى تلقائيًا
    من كل قيد مسّ الخزينة، فلا يمكن أن يختلف عن القيود أبدًا."""
    q = (db.query(CashTransaction).filter(CashTransaction.company_id == company_id))
    if start is not None:
        q = q.filter(CashTransaction.txn_date >= start)
    if end is not None:
        q = q.filter(CashTransaction.txn_date <= end)
    rows = q.order_by(CashTransaction.txn_date.asc(), CashTransaction.id.asc()).all()
    return [{"id": t.id, "date": str(t.txn_date), "direction": t.direction,
             "amount": str(t.amount), "description": t.description,
             "reference_type": t.reference_type, "journal_entry_id": t.journal_entry_id}
            for t in rows]


@scoped.get("/bank-transactions")
def list_bank_transactions(company_id: int, start: Optional[date] = None,
                           end: Optional[date] = None, db: Session = Depends(get_db)):
    """كشف حركات البنك (1200) من جدول bank_transactions — mirror تلقائي من القيود."""
    q = (db.query(BankTransaction).filter(BankTransaction.company_id == company_id))
    if start is not None:
        q = q.filter(BankTransaction.txn_date >= start)
    if end is not None:
        q = q.filter(BankTransaction.txn_date <= end)
    rows = q.order_by(BankTransaction.txn_date.asc(), BankTransaction.id.asc()).all()
    return [{"id": t.id, "date": str(t.txn_date), "direction": t.direction,
             "amount": str(t.amount), "description": t.description,
             "reference_type": t.reference_type, "journal_entry_id": t.journal_entry_id}
            for t in rows]


# ---------------------------------------------------------------- team (Phase 7, صلاحيات المستخدمين)
@scoped.get("/team")
def list_team(company_id: int, db: Session = Depends(get_db)):
    """أعضاء الشركة وأدوارهم — يظهر لكل الأعضاء (الشفافية)، الإدارة للمالك فقط."""
    rows = (
        db.query(CompanyUser, User)
        .join(User, User.id == CompanyUser.user_id)
        .filter(CompanyUser.company_id == company_id)
        .order_by(CompanyUser.id.asc())
        .all()
    )
    return [
        {"user_id": u.id, "full_name": u.full_name, "phone": u.phone,
         "role": cu.role, "is_you": False}
        for cu, u in rows
    ]


@scoped.post("/team/add")
def add_team_member(
    company_id: int,
    phone: str,
    role: str = "staff",
    membership: CompanyUser = Depends(RoleChecker("manage_team")),
    db: Session = Depends(get_db),
):
    """إضافة مستخدم مسجّل (برقم هاتفه) إلى الشركة بدور محدد. المالك فقط."""
    if role not in ROLE_PERMISSIONS:
        raise HTTPException(400, "الدور يجب أن يكون: owner أو accountant أو staff.")
    if membership.role == "owner" and role == "owner":
        # Adding another owner is allowed, but never demote the last owner
        # implicitly here — owners are managed via /team/role.
        pass
    user = db.query(User).filter(User.phone == phone.strip()).one_or_none()
    if user is None:
        raise HTTPException(404, "لا يوجد مستخدم مسجّل بهذا الرقم. اطلب منه إنشاء حساب أولًا.")
    existing = (
        db.query(CompanyUser)
        .filter(CompanyUser.company_id == company_id, CompanyUser.user_id == user.id)
        .one_or_none()
    )
    if existing is not None:
        raise HTTPException(400, "هذا المستخدم عضو في الشركة بالفعل.")
    db.add(CompanyUser(company_id=company_id, user_id=user.id, role=role))
    db.commit()
    return {"status": "ok", "user_id": user.id, "full_name": user.full_name, "role": role}


@scoped.post("/team/role")
def change_member_role(
    company_id: int,
    user_id: int,
    role: str,
    membership: CompanyUser = Depends(RoleChecker("manage_team")),
    db: Session = Depends(get_db),
):
    """تغيير دور عضو موجود. لا يمكن للمالك تغيير دوره هو آخر مالك فيترك الشركة بلا مالك."""
    if role not in ROLE_PERMISSIONS:
        raise HTTPException(400, "الدور يجب أن يكون: owner أو accountant أو staff.")
    target = (
        db.query(CompanyUser)
        .filter(CompanyUser.company_id == company_id, CompanyUser.user_id == user_id)
        .one_or_none()
    )
    if target is None:
        raise HTTPException(404, "العضو غير موجود في هذه الشركة.")
    if target.user_id == membership.user_id and target.role == "owner" and role != "owner":
        owners = (
            db.query(CompanyUser)
            .filter(CompanyUser.company_id == company_id, CompanyUser.role == "owner")
            .count()
        )
        if owners <= 1:
            raise HTTPException(400, "لا يمكن إزالة دور المالك — أنت المالك الوحيد.")
    target.role = role
    db.commit()
    return {"status": "ok", "user_id": user_id, "role": role}


@scoped.post("/team/remove")
def remove_team_member(
    company_id: int,
    user_id: int,
    membership: CompanyUser = Depends(RoleChecker("manage_team")),
    db: Session = Depends(get_db),
):
    """إزالة عضو من الشركة. حماية آخر مالك من إزالة نفسه بالخطأ."""
    target = (
        db.query(CompanyUser)
        .filter(CompanyUser.company_id == company_id, CompanyUser.user_id == user_id)
        .one_or_none()
    )
    if target is None:
        raise HTTPException(404, "العضو غير موجود في هذه الشركة.")
    if target.role == "owner":
        owners = (
            db.query(CompanyUser)
            .filter(CompanyUser.company_id == company_id, CompanyUser.role == "owner")
            .count()
        )
        if owners <= 1:
            raise HTTPException(400, "لا يمكن إزالة المالك الوحيد للشركة.")
    db.delete(target)
    db.commit()
    return {"status": "ok"}


@scoped.get("/team/me")
def my_membership(
    company_id: int,
    membership: CompanyUser = Depends(verify_company_access),
):
    """دور المستخدم الحالي في هذه الشركة — لتخصيص الواجهة حسب الصلاحية."""
    return {"role": membership.role, "permissions": sorted(ROLE_PERMISSIONS.get(membership.role, set()))}


# ---------------------------------------------------------------- notifications (Phase 7, التنبيهات)
@scoped.get("/notifications")
def notifications(company_id: int, db: Session = Depends(get_db)):
    """تنبيهات عملية بسيطة: أصناف تحت حد الطلب أو نافدة، وأرصدة عملاء مستحقة،
    وموردون مستحق لهم — من البيانات الحقيقية مباشرة (بند 84).
    العناصر العاجلة أولًا: النافد (خطأ) ثم المنخفض (تحذير) ثم المستحق للتحصيل."""
    alerts: list[dict] = []

    # 1) المخزون: النافد ثم المنخفض
    products = (
        db.query(Product)
        .filter(Product.company_id == company_id, Product.deleted_at.is_(None))
        .all()
    )
    for p in products:
        stock = float(p.current_stock or 0)
        minimum = float(p.minimum_stock or 0)
        if minimum <= 0:
            continue
        if stock <= 0:
            alerts.append({
                "kind": "stock_out", "severity": "error", "icon": "warning",
                "title": f"نفد المخزون: {p.name}",
                "body": f"الرصيد الحالي صفر (الحد الأدنى {AppFmt_num(minimum)}).",
            })
        elif stock <= minimum:
            alerts.append({
                "kind": "stock_low", "severity": "warning", "icon": "warning",
                "title": f"مخزون منخفض: {p.name}",
                "body": f"الرصيد {AppFmt_num(stock)} — الحد الأدنى {AppFmt_num(minimum)}.",
            })

    # 2) العملاء المستحق لنا لديهم
    from app.models.journal import JournalEntryLine, JournalEntry
    from app.models.accounts import Account
    from app.models.parties import Customer as CustomerModel, Supplier as SupplierModel

    ar_rows = (
        db.query(JournalEntryLine.customer_id, CustomerModel.name,
                 func.coalesce(func.sum(JournalEntryLine.debit) - func.sum(JournalEntryLine.credit), 0))
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .join(CustomerModel, CustomerModel.id == JournalEntryLine.customer_id)
        .filter(
            JournalEntry.company_id == company_id,
            JournalEntryLine.customer_id.isnot(None),
            Account.code == SystemAccountCode.ACCOUNTS_RECEIVABLE.value,
        )
        .group_by(JournalEntryLine.customer_id, CustomerModel.name)
        .all()
    )
    for cid, name, net in ar_rows:
        balance = float(net or 0)
        if balance > 0:
            alerts.append({
                "kind": "receivable", "severity": "info", "icon": "person",
                "title": f"مستحق للتحصيل: {name}",
                "body": f"رصيد مستحق لدينا {AppFmt_num(balance)} ج.م.",
            })

    # 3) الموردون المستحق لهم علينا
    ap_rows = (
        db.query(JournalEntryLine.supplier_id, SupplierModel.name,
                 func.coalesce(func.sum(JournalEntryLine.credit) - func.sum(JournalEntryLine.debit), 0))
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .join(SupplierModel, SupplierModel.id == JournalEntryLine.supplier_id)
        .filter(
            JournalEntry.company_id == company_id,
            JournalEntryLine.supplier_id.isnot(None),
            Account.code == SystemAccountCode.ACCOUNTS_PAYABLE.value,
        )
        .group_by(JournalEntryLine.supplier_id, SupplierModel.name)
        .all()
    )
    for sid, name, net in ap_rows:
        balance = float(net or 0)
        if balance > 0:
            alerts.append({
                "kind": "payable", "severity": "info", "icon": "store",
                "title": f"مستحق الدفع: {name}",
                "body": f"رصيد مستحق لهم {AppFmt_num(balance)} ج.م.",
            })

    severity_order = {"error": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: severity_order.get(a["severity"], 3))
    return {"alerts": alerts, "count": len(alerts)}


def AppFmt_num(v: float) -> str:
    """تنسيق رقمي خفيف للتنبيهات (فواصل آلاف بدون كسور زائدة)."""
    s = f"{v:,.2f}"
    return s[:-3] if s.endswith(".00") else s


# ---------------------------------------------------------------- export PDF/Excel (Phase 6, بند 39/40)
@scoped.get("/export/{report_key}")
def export_report(company_id: int, report_key: str, fmt: str = "pdf",
                  start: Optional[date] = None, end: Optional[date] = None,
                  account_code: Optional[str] = None,
                  membership: CompanyUser = Depends(RoleChecker("export")),
                  db: Session = Depends(get_db)):
    """PDF/Excel لأي تقرير من: sales, purchases, inventory, expenses, vat,
    trial_balance, general_ledger. fmt = pdf | excel (أو xlsx)."""
    builder = EXPORTS.get(report_key)
    if builder is None:
        raise HTTPException(404, "تقرير غير معروف للتصدير.")
    fmt_key = "xlsx" if fmt.lower() in ("excel", "xlsx") else "pdf"
    try:
        spec = builder(db, company_id, start, end) if report_key != "general_ledger" \
            else builder(db, company_id, start, end, account_code)
    except ExportError as e:
        raise HTTPException(400, str(e))

    if fmt_key == "xlsx":
        body = build_xlsx(spec.title, spec.subtitle, spec.sheets)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    else:
        body = build_pdf(spec.title, spec.subtitle, spec.headers, spec.rows, spec.totals)
        media = "application/pdf"
        ext = "pdf"

    ascii_name = f"{spec.file_name}-{date.today().isoformat()}.{ext}"
    # HTTP headers are latin-1: the Arabic filename must be percent-encoded
    # (RFC 5987) or Starlette can't even serialize the response.
    arabic_name = quote(f"{spec.display_name}-{date.today().isoformat()}.{ext}")
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{arabic_name}"
        ),
        "Content-Type": media,
    }
    return Response(content=body, media_type=media, headers=headers)


# ---------------------------------------------------------------- backup / restore (Phase 6, بند 59/60)
@scoped.get("/backup")
def backup_company(
    company_id: int,
    membership: CompanyUser = Depends(RoleChecker("backup")),
    db: Session = Depends(get_db),
):
    """نسخة احتياطية كاملة للشركة في ملف JSON واحد قابل للقراءة (بند 59)."""
    body, disposition = export_backup_file(db, company_id)
    return Response(content=body, media_type="application/json",
                    headers={"Content-Disposition": disposition})


@scoped.post("/restore")
def restore_company(
    company_id: int,
    payload: dict = Body(...),
    membership: CompanyUser = Depends(RoleChecker("backup")),
    db: Session = Depends(get_db),
):
    """استعادة نسخة احتياطية (وضع الاستبدال): يستبدل بيانات الشركة الحالية بالكامل
    بعد التحقق من توازنها محاسبيًا؛ أي خطأ يعني التراجع عن كل شيء (بند 60).
    محتوى ملف النسخة يُرسل JSON في جسم الطلب."""
    try:
        entries = restore_backup(db, company_id, payload)
    except RestoreError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    except Exception:
        db.rollback()
        raise HTTPException(400, "تعذر قراءة النسخة الاحتياطية. تأكد من اختيار ملف صحيح.")
    return {"status": "ok", "journal_entries_restored": entries,
            "message": "تمت الاستعادة بنجاح"}




app.include_router(auth_router)
app.include_router(companies_router)
app.include_router(scoped)
