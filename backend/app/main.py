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
from app.models import Company, Customer, Supplier
from app.models.company import User, CompanyUser
from app.accounting.chart_of_accounts import seed_chart_of_accounts
from app.accounting.engine import AccountingService, AccountingError
from app.accounting.transactions import (
    record_sale, record_purchase, record_customer_payment,
    record_supplier_payment, record_expense,
)
from app.accounting.statements import customer_statement, supplier_statement
from app.accounting.reports import trial_balance, profit_and_loss, balance_sheet, party_ledger_balance
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
            customer_id: Optional[int] = None, db: Session = Depends(get_db)):
    try:
        invoice = record_sale(db, company_id=company_id, entry_date=date.today(), amount=amount,
                               is_credit=is_credit, method=method, customer_id=customer_id)
        db.commit()
        return {"invoice_number": invoice.invoice_number, "status": "ok"}
    except Exception as e:
        _friendly_error(e, db)


@scoped.post("/operations/purchase")
def op_purchase(company_id: int, amount: Decimal, is_credit: bool = False, method: str = "cash",
                 supplier_id: Optional[int] = None, goes_to_inventory: bool = False,
                 db: Session = Depends(get_db)):
    try:
        invoice = record_purchase(db, company_id=company_id, entry_date=date.today(), amount=amount,
                                   is_credit=is_credit, method=method, supplier_id=supplier_id,
                                   goes_to_inventory=goes_to_inventory)
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


app.include_router(auth_router)
app.include_router(companies_router)
app.include_router(scoped)
