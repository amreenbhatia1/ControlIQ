from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core import permissions as P
from app.core.audit import record_audit
from app.core.database import get_db
from app.core.deps import require
from app.core.rate_limit import client_ip, rate_limit
from app.models import User
from app.schemas.entities import AskIn
from app.services import intelligence_service

router = APIRouter(prefix="/intelligence", tags=["Risk Intelligence"])


@router.get("/status", dependencies=[Depends(require(P.INTEL_USE))])
def status(db: Session = Depends(get_db)):
    return intelligence_service.ai_status(db)


@router.post("/ask", dependencies=[Depends(rate_limit("intelligence", 30, 60))])
def ask(body: AskIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require(P.INTEL_USE))):
    ans = intelligence_service.answer_question(db, body.question, body.finding_id)
    record_audit(db, "intelligence.query", actor=user, entity_type="intelligence", entity_id=ans.intent,
                 details={"question": body.question[:300], "mode": ans.mode, "records_used": ans.records_used},
                 ip_address=client_ip(request))
    db.commit()
    return ans.to_dict()


@router.post("/executive-summary", dependencies=[Depends(rate_limit("intelligence", 30, 60))])
def executive_summary(db: Session = Depends(get_db), user: User = Depends(require(P.READ))):
    return intelligence_service.answer_question(db, "Give me an executive summary of the control environment.").to_dict()
