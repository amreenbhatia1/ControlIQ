from sqlalchemy.orm import Session

from app.models import AuditLog, User


def record_audit(
    db: Session,
    action: str,
    *,
    actor: User | None = None,
    entity_type: str = "",
    entity_id: str | int = "",
    details: dict | None = None,
    outcome: str = "success",
    ip_address: str = "",
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else "system",
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details=details or {},
        outcome=outcome,
        ip_address=ip_address,
    )
    db.add(entry)
    return entry
