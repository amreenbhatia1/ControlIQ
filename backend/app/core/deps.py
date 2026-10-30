from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import client_ip
from app.core.security import hash_session_token
from app.core.time import utcnow
from app.models import User, UserSession


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_session_token(token)))
    if session is None or session.expires_at <= utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired or invalid")
    user = session.user
    if not user.is_active or not user.can_login:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account disabled")
    request.state.user = user
    return user


def record_denial(db: Session, user: User, request: Request, reason: str) -> None:
    """Persist an authorisation failure, discarding any uncommitted work from the denied request."""
    db.rollback()
    endpoint = f"{request.method} {request.url.path}"
    record_audit(
        db, "authz.denied", actor=user, entity_type="endpoint", entity_id=endpoint[:60],
        outcome="denied", details={"endpoint": endpoint, "reason": reason}, ip_address=client_ip(request),
    )
    db.commit()


def require(*permissions: str):
    """Dependency factory: the current user must hold every listed permission."""

    def dependency(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        missing = [p for p in permissions if p not in user.permissions]
        if missing:
            detail = f"Your role ({user.role.name}) does not permit this action"
            record_denial(db, user, request, f"missing permission: {', '.join(missing)}")
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail)
        return user

    return dependency
