"""
FastAPI dependencies that:
  1. Identify the calling user from the Bearer token (get_current_user).
  2. Enforce that they actually belong to the company_id in the URL
     (verify_company_access) — this is spec §6/§44's "prevent a user from
     reaching another company's data" requirement, enforced on every
     request rather than trusted from the client.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.models.base import SessionLocal
from app.models.company import User, CompanyUser
from app.auth.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="بيانات الدخول غير صحيحة أو انتهت صلاحيتها. سجّل الدخول مرة أخرى.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user_id = decode_access_token(token)
    if user_id is None:
        raise credentials_error
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).one_or_none()
    if user is None:
        raise credentials_error
    return user


def verify_company_access(
    company_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanyUser:
    """
    Every /companies/{company_id}/... route depends on this. It's what
    actually stops user A from reading/writing company B's data just by
    changing the number in the URL — company_id alone was never enough.
    """
    membership = (
        db.query(CompanyUser)
        .filter(CompanyUser.company_id == company_id, CompanyUser.user_id == current_user.id)
        .one_or_none()
    )
    if membership is None:
        # Deliberately the same 404 whether the company doesn't exist or the
        # user just isn't a member of it — don't leak which companies exist.
        raise HTTPException(status_code=404, detail="الشركة غير موجودة.")
    return membership
