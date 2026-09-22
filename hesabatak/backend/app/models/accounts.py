import enum
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin, CompanyScopedMixin


class AccountNature(str, enum.Enum):
    """
    The accounting 'normal balance' side of an account. This is what lets the
    engine compute a signed balance correctly instead of guessing:
      - DEBIT accounts (Assets, Expenses) increase with a Dr, decrease with a Cr.
      - CREDIT accounts (Liabilities, Equity, Revenue) increase with a Cr, decrease with a Dr.
    """
    DEBIT = "debit"
    CREDIT = "credit"


class AccountType(Base, TimestampMixin):
    __tablename__ = "account_types"

    id = Column(Integer, primary_key=True)
    code = Column(String(20), unique=True, nullable=False)   # ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE, COGS
    name_ar = Column(String(100), nullable=False)
    nature = Column(Enum(AccountNature), nullable=False)


class Account(Base, TimestampMixin, CompanyScopedMixin):
    """
    A single ledger account (chart of accounts line), e.g. 1100 Cash / الخزينة.
    Journal entries always post Dr/Cr against Accounts — never directly against
    invoices, customers, or products (spec §9, §75: Journal Entries are the
    single source of truth for all financial reports).
    """
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    code = Column(String(20), nullable=False)         # e.g. "1100"
    name_ar = Column(String(150), nullable=False)      # e.g. "الخزينة"
    name_en = Column(String(150), nullable=True)        # e.g. "Cash" (for future EN localization, spec §34)
    account_type_id = Column(Integer, ForeignKey("account_types.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    is_system = Column(Boolean, default=False, nullable=False)  # true for accounts the engine depends on (Cash, AR, AP...)
    is_active = Column(Boolean, default=True, nullable=False)

    account_type = relationship("AccountType")


# --- Well-known system account codes the AccountingService relies on. ---
# Using stable codes (not free-text names) means the engine never breaks if
# the user renames "الخزينة" to something else in Settings.
class SystemAccountCode(str, enum.Enum):
    CASH = "1100"
    BANK = "1200"
    ACCOUNTS_RECEIVABLE = "1300"
    INVENTORY = "1400"
    OUTPUT_VAT_PAYABLE = "2150"   # liability: VAT collected on sales, owed to the tax authority
    ACCOUNTS_PAYABLE = "2100"
    INPUT_VAT_RECEIVABLE = "1350"  # asset: VAT paid on purchases, reclaimable
    OWNER_CAPITAL = "3100"
    OWNER_DRAWINGS = "3200"
    SALES_REVENUE = "4100"
    COST_OF_GOODS_SOLD = "5100"
    UNCATEGORIZED_EXPENSE = "6900"
