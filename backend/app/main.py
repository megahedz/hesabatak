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

from fastapi import FastAPI, APIRouter, Depends, HTTPException
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
from app.accounting.inventory import opening_stock_value
from app.models.accounts import SystemAccountCode
from app.auth.security import hash_password, verify_password, create_access_token, SECRET_KEY
from app.auth.dependencies import get_db, get_current_user, verify_company_access

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
def dashboard(company_id: int, db: Session = Depends(get_db)):
    today = date.today()
    month_start = today.replace(day=1)
    cash = party_ledger_balance(db, company_id, SystemAccountCode.CASH.value)
    bank = party_ledger_balance(db, company_id, SystemAccountCode.BANK.value)
    receivable = party_ledger_balance(db, company_id, SystemAccountCode.ACCOUNTS_RECEIVABLE.value)
    payable = party_ledger_balance(db, company_id, SystemAccountCode.ACCOUNTS_PAYABLE.value)
    pl_month = profit_and_loss(db, company_id, start=month_start, end=today)
    return {
        "رصيد_الخزينة": str(cash), "رصيد_البنك": str(bank),
        "لدى_العملاء": str(receivable), "للموردين": str(payable),
        "مبيعات_الشهر": str(pl_month["revenue"]), "المصروفات": str(pl_month["operating_expenses"]),
        "صافي_الربح": str(pl_month["net_profit"]), "العملة": "ج.م",
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
            unit_price: Optional[Decimal] = None, db: Session = Depends(get_db)):
    """One sale. When product_id+quantity are given, the invoice records the
    line, stock is consumed at weighted-average cost, and the computed COGS is
    posted automatically — the caller never sends COGS (spec §9: engine only)."""
    try:
        items = None
        if product_id is not None:
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


@scoped.post("/operations/purchase")
def op_purchase(company_id: int, amount: Decimal, is_credit: bool = False, method: str = "cash",
                 supplier_id: Optional[int] = None, goes_to_inventory: bool = False,
                 vat_amount: Decimal = Decimal("0"),
                 product_id: Optional[int] = None, quantity: Decimal = Decimal("0"),
                 db: Session = Depends(get_db)):
    """One purchase. With product_id+quantity, stock is received at
    amount/quantity as unit cost and the weighted average is re-computed."""
    try:
        items = None
        if product_id is not None:
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


app.include_router(auth_router)
app.include_router(companies_router)
app.include_router(scoped)
