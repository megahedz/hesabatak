from sqlalchemy import Column, Integer, String, Text, ForeignKey
from .base import Base, TimestampMixin, CompanyScopedMixin


class AuditLog(Base, TimestampMixin, CompanyScopedMixin):
    """Every sensitive action, per spec §45: who did what, to what, and what changed."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(50), nullable=False)     # 'create_sale', 'void_invoice', ...
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=True)
    old_value = Column(Text, nullable=True)          # JSON snapshot before
    new_value = Column(Text, nullable=True)          # JSON snapshot after


class AppSetting(Base, TimestampMixin, CompanyScopedMixin):
    __tablename__ = "app_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String(100), nullable=False)
    value = Column(Text, nullable=True)
