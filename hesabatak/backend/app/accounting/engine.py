"""
AccountingService — the ONLY code in the system allowed to create journal
entries (spec §9, §76). Every user-facing action (بيع/شراء/قبض/دفع/مصروف/...)
must go through one of these methods, never write to journal_entries directly.

Design rules enforced here:
  - Every call posts a single JournalEntry whose lines balance exactly
    (sum(debit) == sum(credit)), checked in code, not trusted from callers.
  - All money is Decimal, quantized to 2 decimal places — never float.
  - VAT is posted to its own liability/asset accounts, never mixed into
    Revenue or Expense (spec §33).
  - Nothing here mutates or deletes a prior JournalEntry; corrections are
    made with reverse_journal_entry() which posts an offsetting entry.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from app.models.journal import JournalEntry, JournalEntryLine
from app.accounting.chart_of_accounts import get_account
from app.models.accounts import SystemAccountCode


TWOPLACES = Decimal("0.01")


def money(value) -> Decimal:
    """Coerce any numeric input to a 2-decimal-place Decimal. Never accept float silently for amounts."""
    if isinstance(value, float):
        # A float has almost certainly already lost precision before it got here;
        # convert via str() rather than Decimal(float) to avoid inheriting its noise.
        value = str(value)
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@dataclass
class Line:
    account_code: str
    debit: Decimal = Decimal("0.00")
    credit: Decimal = Decimal("0.00")
    customer_id: Optional[int] = None
    supplier_id: Optional[int] = None


class AccountingError(ValueError):
    """Raised when an operation would violate double-entry integrity or business rules."""


class AccountingService:

    # ------------------------------------------------------------------
    # Core posting primitive — everything else in this class calls this.
    # ------------------------------------------------------------------
    @staticmethod
    def _post(
        db: Session,
        *,
        company_id: int,
        entry_date: date,
        reference_type: str,
        description: str,
        lines: list[Line],
        reference_id: Optional[int] = None,
    ) -> JournalEntry:
        if len(lines) < 2:
            raise AccountingError("A journal entry needs at least two lines.")

        total_debit = sum((l.debit for l in lines), Decimal("0.00"))
        total_credit = sum((l.credit for l in lines), Decimal("0.00"))
        if total_debit != total_credit:
            raise AccountingError(
                f"Journal entry does not balance: Dr {total_debit} != Cr {total_credit} "
                f"(reference_type={reference_type})"
            )
        if total_debit == 0:
            raise AccountingError("A journal entry with zero amount is not allowed.")

        entry = JournalEntry(
            company_id=company_id,
            entry_date=entry_date,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )
        db.add(entry)
        db.flush()  # get entry.id

        for line in lines:
            if line.debit and line.credit:
                raise AccountingError("A single journal line cannot be both debit and credit.")
            if line.debit < 0 or line.credit < 0:
                raise AccountingError("Journal line amounts cannot be negative.")
            account = get_account(db, company_id, line.account_code)
            db.add(JournalEntryLine(
                journal_entry_id=entry.id,
                account_id=account.id,
                debit=line.debit,
                credit=line.credit,
                customer_id=line.customer_id,
                supplier_id=line.supplier_id,
            ))
        db.flush()
        return entry

    @staticmethod
    def reverse_journal_entry(db: Session, *, company_id: int, original_entry: JournalEntry,
                               entry_date: date, description: str) -> JournalEntry:
        """Post the mirror image of an existing entry (spec §46: never edit a posted entry)."""
        reversed_lines = [
            Line(
                account_code=line.account.code,
                debit=line.credit,
                credit=line.debit,
                customer_id=line.customer_id,
                supplier_id=line.supplier_id,
            )
            for line in original_entry.lines
        ]
        entry = AccountingService._post(
            db, company_id=company_id, entry_date=entry_date,
            reference_type=f"reversal_of_{original_entry.reference_type}",
            reference_id=original_entry.id, description=description, lines=reversed_lines,
        )
        entry.is_reversal_of = original_entry.id
        db.flush()
        return entry

    # ------------------------------------------------------------------
    # Sales (spec §10)
    # ------------------------------------------------------------------
    @staticmethod
    def create_sale(
        db: Session, *, company_id: int, entry_date: date,
        amount: Decimal, is_credit: bool, method: str = "cash",
        vat_amount: Decimal = Decimal("0"), cogs_amount: Optional[Decimal] = None,
        customer_id: Optional[int] = None,
        reference_id: Optional[int] = None, description: str = "بيع",
    ) -> JournalEntry:
        """
        amount: the sale value BEFORE VAT (i.e. Sales revenue amount).
        The customer/cash side is debited for amount + vat_amount.
        A credit sale (بيع آجل) must always name a customer_id — you can't owe
        money to "no one" on the books, even if the UI made it optional.
        """
        if is_credit and customer_id is None:
            raise AccountingError("بيع آجل يجب أن يكون مرتبطًا بعميل (customer_id مطلوب).")

        amount = money(amount)
        vat_amount = money(vat_amount)
        receivable_side = SystemAccountCode.ACCOUNTS_RECEIVABLE.value if is_credit else (
            SystemAccountCode.BANK.value if method == "bank" else SystemAccountCode.CASH.value
        )
        total_owed = amount + vat_amount

        lines = [
            Line(account_code=receivable_side, debit=total_owed,
                 customer_id=customer_id if is_credit else None),
            Line(account_code=SystemAccountCode.SALES_REVENUE.value, credit=amount),
        ]
        if vat_amount > 0:
            lines.append(Line(account_code=SystemAccountCode.OUTPUT_VAT_PAYABLE.value, credit=vat_amount))

        entry = AccountingService._post(
            db, company_id=company_id, entry_date=entry_date, reference_type="sale",
            reference_id=reference_id, description=description, lines=lines,
        )

        if cogs_amount is not None and cogs_amount > 0:
            cogs_amount = money(cogs_amount)
            AccountingService._post(
                db, company_id=company_id, entry_date=entry_date, reference_type="sale_cogs",
                reference_id=reference_id, description=f"{description} - تكلفة البضاعة المباعة",
                lines=[
                    Line(account_code=SystemAccountCode.COST_OF_GOODS_SOLD.value, debit=cogs_amount),
                    Line(account_code=SystemAccountCode.INVENTORY.value, credit=cogs_amount),
                ],
            )
        return entry

    # ------------------------------------------------------------------
    # Purchases (spec §11)
    # ------------------------------------------------------------------
    @staticmethod
    def create_purchase(
        db: Session, *, company_id: int, entry_date: date,
        amount: Decimal, is_credit: bool, method: str = "cash",
        vat_amount: Decimal = Decimal("0"), goes_to_inventory: bool = False,
        supplier_id: Optional[int] = None,
        reference_id: Optional[int] = None, description: str = "شراء",
    ) -> JournalEntry:
        if is_credit and supplier_id is None:
            raise AccountingError("شراء آجل يجب أن يكون مرتبطًا بمورد (supplier_id مطلوب).")

        amount = money(amount)
        vat_amount = money(vat_amount)
        payable_side = SystemAccountCode.ACCOUNTS_PAYABLE.value if is_credit else (
            SystemAccountCode.BANK.value if method == "bank" else SystemAccountCode.CASH.value
        )
        debit_account = SystemAccountCode.INVENTORY.value if goes_to_inventory else SystemAccountCode.COST_OF_GOODS_SOLD.value
        total_owed = amount + vat_amount

        lines = [Line(account_code=debit_account, debit=amount)]
        if vat_amount > 0:
            lines.append(Line(account_code=SystemAccountCode.INPUT_VAT_RECEIVABLE.value, debit=vat_amount))
        lines.append(Line(account_code=payable_side, credit=total_owed,
                           supplier_id=supplier_id if is_credit else None))

        return AccountingService._post(
            db, company_id=company_id, entry_date=entry_date, reference_type="purchase",
            reference_id=reference_id, description=description, lines=lines,
        )

    # ------------------------------------------------------------------
    # Payments (spec §12, §13)
    # ------------------------------------------------------------------
    @staticmethod
    def create_customer_payment(db: Session, *, company_id: int, entry_date: date,
                                 amount: Decimal, customer_id: int, method: str = "cash",
                                 reference_id: Optional[int] = None, description: str = "تحصيل من عميل") -> JournalEntry:
        if customer_id is None:
            raise AccountingError("قبض من عميل يجب أن يكون مرتبطًا بعميل (customer_id مطلوب).")
        amount = money(amount)
        cash_side = SystemAccountCode.BANK.value if method == "bank" else SystemAccountCode.CASH.value
        return AccountingService._post(
            db, company_id=company_id, entry_date=entry_date, reference_type="customer_payment",
            reference_id=reference_id, description=description,
            lines=[
                Line(account_code=cash_side, debit=amount),
                Line(account_code=SystemAccountCode.ACCOUNTS_RECEIVABLE.value, credit=amount,
                     customer_id=customer_id),
            ],
        )

    @staticmethod
    def create_supplier_payment(db: Session, *, company_id: int, entry_date: date,
                                 amount: Decimal, supplier_id: int, method: str = "cash",
                                 reference_id: Optional[int] = None, description: str = "سداد لمورد") -> JournalEntry:
        if supplier_id is None:
            raise AccountingError("دفع لمورد يجب أن يكون مرتبطًا بمورد (supplier_id مطلوب).")
        amount = money(amount)
        cash_side = SystemAccountCode.BANK.value if method == "bank" else SystemAccountCode.CASH.value
        return AccountingService._post(
            db, company_id=company_id, entry_date=entry_date, reference_type="supplier_payment",
            reference_id=reference_id, description=description,
            lines=[
                Line(account_code=SystemAccountCode.ACCOUNTS_PAYABLE.value, debit=amount,
                     supplier_id=supplier_id),
                Line(account_code=cash_side, credit=amount),
            ],
        )

    # ------------------------------------------------------------------
    # Expenses (spec §14)
    # ------------------------------------------------------------------
    @staticmethod
    def create_expense(db: Session, *, company_id: int, entry_date: date,
                        amount: Decimal, expense_account_code: str = SystemAccountCode.UNCATEGORIZED_EXPENSE.value,
                        method: str = "cash", reference_id: Optional[int] = None,
                        description: str = "مصروف") -> JournalEntry:
        amount = money(amount)
        cash_side = SystemAccountCode.BANK.value if method == "bank" else SystemAccountCode.CASH.value
        return AccountingService._post(
            db, company_id=company_id, entry_date=entry_date, reference_type="expense",
            reference_id=reference_id, description=description,
            lines=[
                Line(account_code=expense_account_code, debit=amount),
                Line(account_code=cash_side, credit=amount),
            ],
        )

    # ------------------------------------------------------------------
    # Owner capital / drawings (spec §15, §16)
    # ------------------------------------------------------------------
    @staticmethod
    def create_capital(db: Session, *, company_id: int, entry_date: date,
                        amount: Decimal, method: str = "cash",
                        description: str = "إيداع رأس مال") -> JournalEntry:
        amount = money(amount)
        cash_side = SystemAccountCode.BANK.value if method == "bank" else SystemAccountCode.CASH.value
        return AccountingService._post(
            db, company_id=company_id, entry_date=entry_date, reference_type="owner_capital",
            description=description,
            lines=[
                Line(account_code=cash_side, debit=amount),
                Line(account_code=SystemAccountCode.OWNER_CAPITAL.value, credit=amount),
            ],
        )

    @staticmethod
    def create_owner_withdrawal(db: Session, *, company_id: int, entry_date: date,
                                 amount: Decimal, method: str = "cash",
                                 description: str = "سحب شخصي") -> JournalEntry:
        amount = money(amount)
        cash_side = SystemAccountCode.BANK.value if method == "bank" else SystemAccountCode.CASH.value
        return AccountingService._post(
            db, company_id=company_id, entry_date=entry_date, reference_type="owner_withdrawal",
            description=description,
            lines=[
                Line(account_code=SystemAccountCode.OWNER_DRAWINGS.value, debit=amount),
                Line(account_code=cash_side, credit=amount),
            ],
        )

    # ------------------------------------------------------------------
    # Transfer between own accounts (spec §17) — never Revenue/Expense.
    # ------------------------------------------------------------------
    @staticmethod
    def create_transfer(db: Session, *, company_id: int, entry_date: date,
                         amount: Decimal, from_code: str, to_code: str,
                         description: str = "تحويل بين الحسابات") -> JournalEntry:
        if from_code == to_code:
            raise AccountingError("Cannot transfer an account to itself.")
        amount = money(amount)
        return AccountingService._post(
            db, company_id=company_id, entry_date=entry_date, reference_type="transfer",
            description=description,
            lines=[
                Line(account_code=to_code, debit=amount),
                Line(account_code=from_code, credit=amount),
            ],
        )
