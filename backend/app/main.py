"""
حساباتك API — Phase 4: real authentication.

Every /companies/{company_id}/... route now requires a valid Bearer token
AND membership in that specific company (via verify_company_access) —
spec §44/§6. /auth/register and /auth/login are open; POST /companies
requires login (creates the company AND makes the caller its owner).
"""
import os
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Body
from sqlalchemy import func
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.models.base import Base, engine, SessionLocal
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
from app.accounting.detailed_reports import sales_report, purchases_report, inventory_report, expense_report
from app.accounting.dashboard_stats import monthly_sales_series, period_purchases
from app.accounting.exports import (
    build_pdf, build_xlsx, EXPORTS, ExportError,
)
from app.accounting.backup import export_backup_file, restore_backup, RestoreError
from app.accounting.inventory import opening_stock_value
from app.models.accounts import SystemAccountCode
from app.auth.security import hash_password, verify_password, create_access_token, SECRET_KEY
from app.auth.dependencies import get_db, get_current_user, verify_company_access
from fastapi import Response
from urllib.parse import quote

app = FastAPI(title="حساباتك API")


@app.on_event("startup")
def on_startup():
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


@auth_router.post("/register")
def register(full_name: str, phone: str, password: str, db: Session = Depends(get_db)):
    if len(password) < 6:
        raise HTTPException(400, "كلمة المرور يجب أن تكون 6 أحرف على الأقل.")
    existing = db.query(User).filter(User.phone == phone).one_or_none()
    if existing is not None:
        raise HTTPException(400, "رقم الهاتف مستخدم بالفعل.")
    user = User(full_name=full_name, phone=phone, password_hash=hash_password(password))
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
    return {"id": current_user.id, "full_name": current_user.full_name, "phone": current_user.phone}


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
    db.commit()
    return {"id": company.id, "name": company.name}


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
    }


@scoped.post("/settings")
def update_settings(company_id: int,
                    vat_enabled: Optional[bool] = None,
                    vat_rate: Optional[Decimal] = None,
                    inventory_enabled: Optional[bool] = None,
                    fiscal_year_start_month: Optional[int] = None,
                    name: Optional[str] = None,
                    business_type: Optional[str] = None,
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
    db.commit()
    return get_settings(company_id, db)


# ---------------------------------------------------------------- products
@scoped.get("/products")
def list_products(company_id: int, db: Session = Depends(get_db)):
    products = db.query(Product).filter(Product.company_id == company_id,
                                        Product.deleted_at.is_(None)).all()
    return [{
        "id": p.id, "name": p.name, "sku": p.sku, "barcode": p.barcode,
        "unit": p.unit, "purchase_price": str(p.purchase_price),
        "selling_price": str(p.selling_price), "current_stock": str(p.current_stock),
        "minimum_stock": str(p.minimum_stock),
    } for p in products]


@scoped.post("/products")
def create_product(company_id: int, name: str, sku: Optional[str] = None,
                   barcode: Optional[str] = None, unit: str = "قطعة",
                   purchase_price: Decimal = Decimal("0"), selling_price: Decimal = Decimal("0"),
                   opening_stock_qty: Decimal = Decimal("0"),
                   minimum_stock: Decimal = Decimal("0"),
                   db: Session = Depends(get_db)):
    """
    Create a product. If it starts with stock already on hand, the stock is
    received at `purchase_price` and its value is posted as
    Inventory Dr / Owner Capital Cr (owner contribution, spec §71 assumption)
    — one DB transaction for product + movement + journal entry.
    """
    if not name.strip():
        raise HTTPException(400, "اسم المنتج مطلوب.")
    if purchase_price < 0 or selling_price < 0 or opening_stock_qty < 0:
        raise HTTPException(400, "الأسعار والكميات لا يمكن أن تكون سالبة.")

    product = Product(
        company_id=company_id, name=name.strip(), sku=sku, barcode=barcode,
        unit=unit, purchase_price=purchase_price, selling_price=selling_price,
        minimum_stock=minimum_stock, current_stock=0,
    )
    db.add(product)
    db.flush()

    if opening_stock_qty > 0:
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
def create_customer(company_id: int, name: str, phone: Optional[str] = None,
                     opening_balance: Decimal = Decimal("0"), db: Session = Depends(get_db)):
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
def create_supplier(company_id: int, name: str, phone: Optional[str] = None,
                     opening_balance: Decimal = Decimal("0"), db: Session = Depends(get_db)):
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
@scoped.post("/operations/sale")
def op_sale(company_id: int, amount: Decimal, is_credit: bool = False, method: str = "cash",
            customer_id: Optional[int] = None, vat_amount: Decimal = Decimal("0"),
            product_id: Optional[int] = None, quantity: Decimal = Decimal("0"),
            unit_price: Optional[Decimal] = None,
            items_json: Optional[str] = None, db: Session = Depends(get_db)):
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
        return {"invoice_number": invoice.invoice_number, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


def _parse_items_json(raw: str) -> list[dict]:
    """Parse the mobile client's items payload. Values arrive as strings via
    query params; numbers are coerced so record_sale can validate them."""
    import json
    try:
        rows = json.loads(raw)
        assert isinstance(rows, list) and rows
    except Exception:
        raise AccountingError("بنود الفاتورة غير صالحة.")
    parsed = []
    for r in rows:
        try:
            parsed.append({
                "product_id": int(r["product_id"]),
                "quantity": Decimal(str(r["quantity"])),
                "unit_price": Decimal(str(r["unit_price"])),
            })
        except Exception:
            raise AccountingError("بنود الفاتورة غير صالحة.")
    return parsed


@scoped.post("/operations/purchase")
def op_purchase(company_id: int, amount: Decimal, is_credit: bool = False, method: str = "cash",
                 supplier_id: Optional[int] = None, goes_to_inventory: bool = False,
                 vat_amount: Decimal = Decimal("0"),
                 product_id: Optional[int] = None, quantity: Decimal = Decimal("0"),
                 items_json: Optional[str] = None,
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
        return {"invoice_number": invoice.invoice_number, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


@scoped.post("/operations/customer-payment")
def op_customer_payment(company_id: int, amount: Decimal, customer_id: int, method: str = "cash",
                         db: Session = Depends(get_db)):
    try:
        payment = record_customer_payment(db, company_id=company_id, entry_date=date.today(),
                                           amount=amount, customer_id=customer_id, method=method)
        db.commit()
        return {"payment_id": payment.id, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


@scoped.post("/operations/supplier-payment")
def op_supplier_payment(company_id: int, amount: Decimal, supplier_id: int, method: str = "cash",
                         db: Session = Depends(get_db)):
    try:
        payment = record_supplier_payment(db, company_id=company_id, entry_date=date.today(),
                                           amount=amount, supplier_id=supplier_id, method=method)
        db.commit()
        return {"payment_id": payment.id, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


@scoped.post("/operations/expense")
def op_expense(company_id: int, amount: Decimal, method: str = "cash",
               expense_account_code: str = SystemAccountCode.UNCATEGORIZED_EXPENSE.value,
               notes: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        expense = record_expense(db, company_id=company_id, entry_date=date.today(), amount=amount,
                                  expense_account_code=expense_account_code, method=method, notes=notes)
        db.commit()
        return {"expense_id": expense.id, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


@scoped.post("/operations/capital")
def op_capital(company_id: int, amount: Decimal, method: str = "cash", db: Session = Depends(get_db)):
    try:
        entry = AccountingService.create_capital(db, company_id=company_id, entry_date=date.today(),
                                                   amount=amount, method=method)
        db.commit()
        return {"journal_entry_id": entry.id, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


@scoped.post("/operations/owner-withdrawal")
def op_owner_withdrawal(company_id: int, amount: Decimal, method: str = "cash", db: Session = Depends(get_db)):
    try:
        entry = AccountingService.create_owner_withdrawal(db, company_id=company_id, entry_date=date.today(),
                                                            amount=amount, method=method)
        db.commit()
        return {"journal_entry_id": entry.id, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


@scoped.post("/operations/transfer")
def op_transfer(company_id: int, amount: Decimal, from_code: str, to_code: str, db: Session = Depends(get_db)):
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
                 db: Session = Depends(get_db)):
    """تقرير المبيعات التفصيلي: كل فاتورة ببنودها + إجماليات الفترة (بند 39)."""
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
                     db: Session = Depends(get_db)):
    """تقرير المشتريات التفصيلي: كل فاتورة ببنودها + إجماليات الفترة (بند 39)."""
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
                    db: Session = Depends(get_db)):
    """تقرير المصروفات مجمّعة على حسابات المصروفات، من القيود مباشرة."""
    rep = expense_report(db, company_id, start, end)
    return {"rows": [{"code": r["code"], "name_ar": r["name_ar"], "amount": str(r["amount"])}
                     for r in rep["rows"]],
            "total": str(rep["total"])}


# ---------------------------------------------------------------- export PDF/Excel (Phase 6, بند 39/40)
@scoped.get("/export/{report_key}")
def export_report(company_id: int, report_key: str, fmt: str = "pdf",
                  start: Optional[date] = None, end: Optional[date] = None,
                  account_code: Optional[str] = None,
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
def backup_company(company_id: int, db: Session = Depends(get_db)):
    """نسخة احتياطية كاملة للشركة في ملف JSON واحد قابل للقراءة (بند 59)."""
    body, disposition = export_backup_file(db, company_id)
    return Response(content=body, media_type="application/json",
                    headers={"Content-Disposition": disposition})


@scoped.post("/restore")
def restore_company(company_id: int, payload: dict = Body(...),
                    db: Session = Depends(get_db)):
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
