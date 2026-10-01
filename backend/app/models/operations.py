"""
Cloud-architecture entities (mandatory entity list): financial years,
fixed assets, bank accounts, and the cash/bank transaction ledgers.

Design note — one source of truth, zero double-entry duplication:
every money movement is a JournalEntry (the single accounting truth).
CashTransaction / BankTransaction are REFLECTION rows derived automatically
from each posted entry by AccountingService._post (see engine.py) so the
app can list cash/bank statements without re-deriving them client-side.
They carry a FK to the entry, so restoring/auditing stays consistent.

All are company-scoped with real foreign keys (multi-company isolation).
"""
from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, Date, Boolean, Text, UniqueConstraint
from .base import Base, TimestampMixin, CompanyScopedMixin


class FinancialYear(Base, TimestampMixin, CompanyScopedMixin):
    """One fiscal year per company (starts per company.fiscal_year_start_month)."""
    __tablename__ = "financial_years"
    __table_args__ = (
        UniqueConstraint("company_id", "start_date", name="uq_fy_start_per_company"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)          # e.g. "2026"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_closed = Column(Boolean, default=False, nullable=False)  # closed years are read-only


class FixedAsset(Base, TimestampMixin, CompanyScopedMixin):
    """A named fixed asset (ثلاجة عرض، عربية...) with its cost and the
    cash/bank account it was paid from. The accounting side is the journal
    entry (Asset Dr / Cash-Bank Cr) referenced here."""
    __tablename__ = "fixed_assets"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    notes = Column(Text, nullable=True)
    acquisition_date = Column(Date, nullable=False)
    cost = Column(Numeric(18, 2), nullable=False)
    from_code = Column(String(20), nullable=False)     # '1100' cash or '1200' bank
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)


class BankAccount(Base, TimestampMixin, CompanyScopedMixin):
    """Bank accounts (البنوك) — one row per bank the company deals with.
    The ledger account 1200 (Bank) remains the single accounting truth;
    this table names the banks for the UI and future per-bank statements."""
    __tablename__ = "bank_accounts"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)          # البنك الأهلي، بنك مصر...
    account_number = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)


class CashTransaction(Base, TimestampMixin, CompanyScopedMixin):
    """Reflection of every journal line hitting the Cash account (1100).
    direction: 'in' (debit) | 'out' (credit)."""
    __tablename__ = "cash_transactions"

    id = Column(Integer, primary_key=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False, index=True)
    txn_date = Column(Date, nullable=False, index=True)
    direction = Column(String(3), nullable=False)       # 'in' | 'out'
    amount = Column(Numeric(18, 2), nullable=False)
    description = Column(String(255), nullable=False)
    reference_type = Column(String(30), nullable=False)


class BankTransaction(Base, TimestampMixin, CompanyScopedMixin):
    """Reflection of every journal line hitting the Bank account (1200).
    direction: 'in' (debit) | 'out' (credit)."""
    __tablename__ = "bank_transactions"

    id = Column(Integer, primary_key=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False, index=True)
    txn_date = Column(Date, nullable=False, index=True)
    direction = Column(String(3), nullable=False)       # 'in' | 'out'
    amount = Column(Numeric(18, 2), nullable=False)
    description = Column(String(255), nullable=False)
    reference_type = Column(String(30), nullable=False)
