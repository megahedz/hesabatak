import enum
from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, Enum, Date
from .base import Base, TimestampMixin, CompanyScopedMixin


class ProductCategory(Base, TimestampMixin, CompanyScopedMixin):
    __tablename__ = "product_categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)


class Product(Base, TimestampMixin, CompanyScopedMixin):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    sku = Column(String(50), nullable=True)
    barcode = Column(String(50), nullable=True)
    category_id = Column(Integer, ForeignKey("product_categories.id"), nullable=True)
    unit = Column(String(30), nullable=False, default="قطعة")
    purchase_price = Column(Numeric(18, 2), nullable=False, default=0)  # last/avg cost, used for weighted-average COGS
    selling_price = Column(Numeric(18, 2), nullable=False, default=0)
    current_stock = Column(Numeric(18, 3), nullable=False, default=0)
    minimum_stock = Column(Numeric(18, 3), nullable=False, default=0)
    tax_rate = Column(Numeric(5, 2), nullable=True)


class StockMovementType(str, enum.Enum):
    PURCHASE_IN = "purchase_in"
    SALE_OUT = "sale_out"
    ADJUSTMENT = "adjustment"


class StockMovement(Base, TimestampMixin, CompanyScopedMixin):
    """
    Immutable log of every stock change, with the weighted-average unit cost
    at the time of the movement — this is what makes COGS auditable instead
    of just a number the app claims.
    """
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    movement_date = Column(Date, nullable=False)
    movement_type = Column(Enum(StockMovementType), nullable=False)
    quantity = Column(Numeric(18, 3), nullable=False)          # always positive; direction implied by movement_type
    unit_cost = Column(Numeric(18, 4), nullable=False)          # weighted-average cost at time of movement
    reference_type = Column(String(30), nullable=True)
    reference_id = Column(Integer, nullable=True)
