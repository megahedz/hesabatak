from sqlalchemy import Column, Integer, String, Numeric, DateTime
from .base import Base, TimestampMixin, CompanyScopedMixin


class Subscription(Base, TimestampMixin, CompanyScopedMixin):
    """اشتراك الشركة (Phase 8) — اشتراك واحد لكل شركة.

    status: trialing (تجربة مجانية) / active (مدفوع) / past_due (منتهي غير مدفوع)
    provider: manual (تفعيل يدوي مؤقتًا) / stripe (بعد ربط بوابة الدفع)
    """
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    status = Column(String(20), nullable=False, default="trialing")
    provider = Column(String(20), nullable=False, default="manual")
    plan = Column(String(50), nullable=False, default="monthly")
    amount = Column(Numeric(10, 2), nullable=False, default=0)  # ج.م شهريًا
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
