from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import client_ip, rate_limit
from app.core.security import hash_session_token, new_session_token, session_expiry, verify_password
from app.core.time import utcnow
from app.models import User, UserSession
from app.schemas.entities import MeOut

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1, max_length=256)


@router.post("/login", response_model=MeOut, dependencies=[Depends(rate_limit("login", 10, 60))])
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    settings = get_settings()
    ip = client_ip(request)
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    valid = verify_password(body.password, user.password_hash if user else None)
    if user is None or not valid or not user.is_active or not user.can_login:
        record_audit(db, "auth.login", entity_type="user", entity_id=body.email[:60], outcome="failure", ip_address=ip)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at < utcnow()))
    token = new_session_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=session_expiry(),
            ip_address=ip,
            user_agent=(request.headers.get("user-agent") or "")[:255],
        )
    )
    user.last_login_at = utcnow()
    record_audit(db, "auth.login", actor=user, entity_type="user", entity_id=user.id, ip_address=ip)
    db.commit()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    return user


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_session_token(token)))
        if session:
            record_audit(db, "auth.logout", actor=session.user, entity_type="user", entity_id=session.user_id,
                         ip_address=client_ip(request))
            db.delete(session)
            db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"message": "Signed out"}


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return user
