from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, Date, CheckConstraint
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin, CompanyScopedMixin


class JournalEntry(Base, TimestampMixin, CompanyScopedMixin):
    """
    One accounting event (a "قيد"). Always has >=2 lines whose debits equal
    credits (enforced in code by AccountingService, never left to the UI).

    Per spec §46/§47: journal entries are never hard-edited or hard-deleted
    once posted. To correct one, the engine posts a REVERSING entry and,
    if needed, a new corrected entry — so the audit trail always shows what
    really happened and when.
    """
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True)
    entry_date = Column(Date, nullable=False)          # posting date used in reports
    reference_type = Column(String(30), nullable=False)  # 'sale' | 'purchase' | 'customer_payment' | ...
    reference_id = Column(Integer, nullable=True)         # id of the source document (invoice, payment, ...)
    description = Column(String(255), nullable=False)
    is_reversal_of = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)

    lines = relationship("JournalEntryLine", back_populates="entry", cascade="all, delete-orphan")


class JournalEntryLine(Base, TimestampMixin):
    __tablename__ = "journal_entry_lines"

    id = Column(Integer, primary_key=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    debit = Column(Numeric(18, 2), nullable=False, default=0)
    credit = Column(Numeric(18, 2), nullable=False, default=0)

    # Subsidiary-ledger dimension: which customer/supplier this line belongs to,
    # so a customer/supplier statement (كشف حساب) can be computed directly from
    # journal entries — the same source of truth as every other report (spec §75) —
    # instead of a second, separately-maintained running balance that can drift.
    # Only ever set on the AR line of a sale/payment, or the AP line of a
    # purchase/payment; every other line leaves these null.
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True, index=True)

    entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account")

    __table_args__ = (
        # A line is either a debit line or a credit line, never both, and never negative.
        CheckConstraint("debit >= 0 AND credit >= 0", name="ck_line_non_negative"),
        CheckConstraint("(debit = 0) OR (credit = 0)", name="ck_line_single_sided"),
    )
