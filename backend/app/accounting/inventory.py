"""
Inventory (spec §18): weighted-average costing with an immutable
stock_movements audit trail.

Rule chosen for SMEs (spec §71 assumption):
  - Every purchase into inventory re-computes the weighted-average unit cost:
        new_avg = (current_qty * avg_cost + purchased_qty * unit_cost)
                  / (current_qty + purchased_qty)
  - Every sale consumes stock at the current weighted-average cost; the
    resulting COGS amount is what the accounting engine posts
    (COGS Dr / Inventory Cr).
  - Selling more than is on hand is rejected (spec §48): negative inventory
    would silently corrupt both the stock count and COGS.
Money math is Decimal throughout (spec §72).
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from app.models.inventory import Product, StockMovement, StockMovementType
from app.accounting.engine import AccountingError

COST_PLACES = Decimal("0.0001")   # unit costs keep 4 decimals internally
MONEY_PLACES = Decimal("0.01")
QTY_PLACES = Decimal("0.001")


def _q(value: Decimal, quantum: Decimal) -> Decimal:
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def compute_new_average(current_qty: Decimal, current_avg_cost: Decimal,
                        incoming_qty: Decimal, incoming_unit_cost: Decimal) -> Decimal:
    """Weighted average after a purchase. Pure function so it's unit-testable."""
    total_qty = current_qty + incoming_qty
    if total_qty <= 0:
        raise AccountingError("إجمالي الكمية بعد الشراء يجب أن يكون أكبر من صفر.")
    if current_qty <= 0:
        return _q(incoming_unit_cost, COST_PLACES)
    total_value = current_qty * current_avg_cost + incoming_qty * incoming_unit_cost
    return _q(total_value / total_qty, COST_PLACES)


def receive_stock(db: Session, *, company_id: int, entry_date: date, product: Product,
                  quantity: Decimal, unit_cost: Decimal,
                  reference_type: Optional[str] = None, reference_id: Optional[int] = None,
                  movement_type: StockMovementType = StockMovementType.PURCHASE_IN) -> Decimal:
    """
    Add stock to a product at `unit_cost`, re-compute the weighted average,
    and log the movement. Returns the movement's total value (qty * unit_cost).
    Callers run inside the same DB transaction as the purchase journal entry.
    """
    quantity = _q(Decimal(quantity), QTY_PLACES)
    unit_cost = _q(Decimal(unit_cost), COST_PLACES)
    if quantity <= 0:
        raise AccountingError("كمية الشراء يجب أن تكون أكبر من صفر.")
    if unit_cost < 0:
        raise AccountingError("تكلفة الوحدة لا يمكن أن تكون سالبة.")

    current_qty = _q(Decimal(product.current_stock or 0), QTY_PLACES)
    current_avg = _q(Decimal(product.purchase_price or 0), COST_PLACES)

    new_avg = compute_new_average(current_qty, current_avg, quantity, unit_cost)
    product.current_stock = current_qty + quantity
    product.purchase_price = _q(new_avg, COST_PLACES)

    db.add(StockMovement(
        company_id=company_id, product_id=product.id, movement_date=entry_date,
        movement_type=movement_type, quantity=quantity, unit_cost=unit_cost,
        reference_type=reference_type, reference_id=reference_id,
    ))
    return _q(quantity * unit_cost, MONEY_PLACES)


def consume_stock(db: Session, *, company_id: int, entry_date: date, product: Product,
                  quantity: Decimal, reference_type: Optional[str] = None,
                  reference_id: Optional[int] = None) -> Decimal:
    """
    Remove sold stock at the current weighted-average cost and log the
    movement. Returns the COGS amount to post (qty * avg cost).
    Raises if the company is trying to sell more than it holds.
    """
    quantity = _q(Decimal(quantity), QTY_PLACES)
    if quantity <= 0:
        raise AccountingError("كمية البيع يجب أن تكون أكبر من صفر.")

    current_qty = _q(Decimal(product.current_stock or 0), QTY_PLACES)
    if quantity > current_qty:
        raise AccountingError(
            f"الكمية المطلوبة من «{product.name}» أكبر من المخزون المتاح "
            f"({current_qty} {product.unit})."
        )
    avg = _q(Decimal(product.purchase_price or 0), COST_PLACES)
    cogs = _q(quantity * avg, MONEY_PLACES)

    product.current_stock = current_qty - quantity
    db.add(StockMovement(
        company_id=company_id, product_id=product.id, movement_date=entry_date,
        movement_type=StockMovementType.SALE_OUT, quantity=quantity, unit_cost=avg,
        reference_type=reference_type, reference_id=reference_id,
    ))
    return cogs


def opening_stock_value(db: Session, *, company_id: int, entry_date: date,
                        product: Product, quantity: Decimal, unit_cost: Decimal) -> Decimal:
    """
    First-time stock for a product created with stock already on hand.
    Logged as an ADJUSTMENT movement; the matching credit side (Owner
    Capital — treating opening goods as an owner contribution, spec §71
    assumption) is posted by the API layer via the engine.
    """
    return receive_stock(
        db, company_id=company_id, entry_date=entry_date, product=product,
        quantity=quantity, unit_cost=unit_cost,
        reference_type="opening_stock", movement_type=StockMovementType.ADJUSTMENT,
    )
