"""
Default chart of accounts, created automatically for every new company
(spec §8). Codes are stable and are what SystemAccountCode in
app/models/accounts.py refers to — renaming an account's Arabic label in
Settings later must never break the engine, only the code does.
"""
from sqlalchemy.orm import Session
from app.models.accounts import Account, AccountType, AccountNature, SystemAccountCode

ACCOUNT_TYPES = [
    ("ASSET", "أصول", AccountNature.DEBIT),
    ("LIABILITY", "خصوم", AccountNature.CREDIT),
    ("EQUITY", "حقوق ملكية", AccountNature.CREDIT),
    ("REVENUE", "إيرادات", AccountNature.CREDIT),
    ("COGS", "تكلفة المبيعات", AccountNature.DEBIT),
    ("EXPENSE", "مصروفات", AccountNature.DEBIT),
]

# (code, name_ar, name_en, type_code, is_system)
DEFAULT_ACCOUNTS = [
    ("1000", "الأصول", "Assets", "ASSET", False),
    (SystemAccountCode.CASH.value, "الخزينة", "Cash", "ASSET", True),
    (SystemAccountCode.BANK.value, "البنك", "Bank", "ASSET", True),
    (SystemAccountCode.ACCOUNTS_RECEIVABLE.value, "أرصدة العملاء", "Accounts Receivable", "ASSET", True),
    (SystemAccountCode.INPUT_VAT_RECEIVABLE.value, "ضريبة القيمة المضافة المدفوعة", "Input VAT", "ASSET", True),
    (SystemAccountCode.INVENTORY.value, "المخزون", "Inventory", "ASSET", True),
    ("1500", "الأصول الثابتة", "Fixed Assets", "ASSET", False),

    ("2000", "الخصوم", "Liabilities", "LIABILITY", False),
    (SystemAccountCode.ACCOUNTS_PAYABLE.value, "أرصدة الموردين", "Accounts Payable", "LIABILITY", True),
    (SystemAccountCode.OUTPUT_VAT_PAYABLE.value, "ضريبة القيمة المضافة المحصلة", "Output VAT", "LIABILITY", True),
    ("2200", "قروض", "Loans", "LIABILITY", False),

    ("3000", "حقوق الملكية", "Equity", "EQUITY", False),
    (SystemAccountCode.OWNER_CAPITAL.value, "رأس مال المالك", "Owner Capital", "EQUITY", True),
    (SystemAccountCode.OWNER_DRAWINGS.value, "مسحوبات شخصية", "Owner Drawings", "EQUITY", True),

    ("4000", "الإيرادات", "Revenue", "REVENUE", False),
    (SystemAccountCode.SALES_REVENUE.value, "المبيعات", "Sales", "REVENUE", True),
    ("4200", "إيرادات أخرى", "Other Revenue", "REVENUE", False),

    ("5000", "تكلفة المبيعات", "Cost of Sales", "COGS", False),
    (SystemAccountCode.COST_OF_GOODS_SOLD.value, "تكلفة البضاعة المباعة", "Cost of Goods Sold", "COGS", True),

    ("6000", "المصروفات", "Expenses", "EXPENSE", False),
    ("6100", "الإيجار", "Rent", "EXPENSE", False),
    ("6200", "الكهرباء", "Electricity", "EXPENSE", False),
    ("6300", "المرتبات", "Salaries", "EXPENSE", False),
    ("6400", "المواصلات", "Transportation", "EXPENSE", False),
    ("6500", "الصيانة", "Maintenance", "EXPENSE", False),
    ("6600", "التسويق", "Marketing", "EXPENSE", False),
    (SystemAccountCode.UNCATEGORIZED_EXPENSE.value, "مصروفات أخرى", "Other Expenses", "EXPENSE", True),
]


def ensure_account_types(db: Session) -> dict[str, AccountType]:
    existing = {t.code: t for t in db.query(AccountType).all()}
    for code, name_ar, nature in ACCOUNT_TYPES:
        if code not in existing:
            t = AccountType(code=code, name_ar=name_ar, nature=nature)
            db.add(t)
            db.flush()
            existing[code] = t
    return existing


def seed_chart_of_accounts(db: Session, company_id: int) -> None:
    """Create the default chart of accounts for a newly created company."""
    types = ensure_account_types(db)
    for code, name_ar, name_en, type_code, is_system in DEFAULT_ACCOUNTS:
        db.add(Account(
            company_id=company_id,
            code=code,
            name_ar=name_ar,
            name_en=name_en,
            account_type_id=types[type_code].id,
            is_system=is_system,
        ))
    db.flush()


def get_account(db: Session, company_id: int, code: str) -> Account:
    account = (
        db.query(Account)
        .filter(Account.company_id == company_id, Account.code == code)
        .one_or_none()
    )
    if account is None:
        raise ValueError(f"System account with code {code} not found for company {company_id}. "
                          f"Was seed_chart_of_accounts() run for this company?")
    return account
