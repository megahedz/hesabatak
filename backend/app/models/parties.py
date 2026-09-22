from sqlalchemy import Column, Integer, String, Numeric, Text
from .base import Base, TimestampMixin, CompanyScopedMixin


class Customer(Base, TimestampMixin, CompanyScopedMixin):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    phone = Column(String(30), nullable=True)
    address = Column(String(255), nullable=True)
    tax_id = Column(String(50), nullable=True)
    opening_balance = Column(Numeric(18, 2), nullable=False, default=0)  # what they owed before day 1
    credit_limit = Column(Numeric(18, 2), nullable=True)
    notes = Column(Text, nullable=True)


class Supplier(Base, TimestampMixin, CompanyScopedMixin):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    phone = Column(String(30), nullable=True)
    address = Column(String(255), nullable=True)
    tax_id = Column(String(50), nullable=True)
    opening_balance = Column(Numeric(18, 2), nullable=False, default=0)
    notes = Column(Text, nullable=True)
