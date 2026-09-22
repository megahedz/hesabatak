from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    full_name = Column(String(150), nullable=False)
    phone = Column(String(30), unique=True, nullable=False)
    email = Column(String(150), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    business_type = Column(String(100), nullable=True)  # ورشة / محل / مقاولات ...
    currency = Column(String(10), nullable=False, default="EGP")
    fiscal_year_start_month = Column(Integer, nullable=False, default=1)  # 1..12
    vat_enabled = Column(Boolean, default=False, nullable=False)
    vat_rate = Column(Numeric(5, 2), nullable=False, default=0)  # e.g. 14.00 for Egypt's standard VAT
    inventory_enabled = Column(Boolean, default=False, nullable=False)
    is_demo = Column(Boolean, default=False, nullable=False)  # spec §58: demo data fully separated


class CompanyUser(Base, TimestampMixin):
    """Join table: which users belong to which company, and their role (multi-company, spec §7)."""
    __tablename__ = "company_users"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(30), nullable=False, default="owner")  # owner / accountant / staff
