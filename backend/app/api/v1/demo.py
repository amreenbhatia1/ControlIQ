import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.serializers import evidence_out
from app.core import permissions as P
from app.core.audit import record_audit
from app.core.database import get_db
from app.core.deps import require
from app.core.rate_limit import client_ip, rate_limit
from app.models import User
from app.schemas.entities import DemoResetIn
from app.seed.seeder import seed_environment
from app.services import demo_service
from app.services.assessment_service import AssessmentInProgressError

router = APIRouter(prefix="/demo", tags=["Demo Scenarios"])


@router.get("/status", dependencies=[Depends(require(P.READ))])
def status(db: Session = Depends(get_db)):
    return {"scenario": demo_service.scenario_status(db), "environment": demo_service.environment_stats(db)}


@router.post("/reset", dependencies=[Depends(rate_limit("demo_reset", 3, 300))])
def reset(body: DemoResetIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require(P.DEMO_RESET))):
    if body.confirm != "RESET":
        raise HTTPException(422, "Type RESET to confirm the environment reset")
    try:
        result = seed_environment(db, log=lambda m: None, actor=user)
    except AssessmentInProgressError as exc:
        raise HTTPException(409, str(exc)) from exc
    record_audit(db, "demo.reset", actor=user, entity_type="environment", entity_id="alphabetabank", ip_address=client_ip(request))
    db.commit()
    return {"message": "Demo environment reset to the synthetic baseline", **result,
            "environment": demo_service.environment_stats(db)}


@router.post("/scenarios/mfa-failure")
def mfa_failure(request: Request, db: Session = Depends(get_db), user: User = Depends(require(P.DEMO_MANAGE))):
    ev = demo_service.trigger_mfa_failure(db, user, client_ip(request))
    return {"message": "Identity connector delivered a privileged account export with MFA gaps", "evidence": evidence_out(ev)}


@router.get("/scenarios/mfa-remediated-evidence", dependencies=[Depends(require(P.READ))])
def remediated_template():
    payload = demo_service.remediated_mfa_payload()
    return Response(json.dumps(payload, indent=2), media_type="application/json", headers={
        "Content-Disposition": 'attachment; filename="privileged_accounts_IDP-CORE-001_remediated.json"'})


@router.post("/scenarios/mfa-remediation-upload")
def mfa_remediation_upload(request: Request, db: Session = Depends(get_db), user: User = Depends(require(P.EVIDENCE_UPLOAD))):
    ev = demo_service.upload_remediated_mfa_evidence(db, user, client_ip(request))
    return {"message": "Updated evidence uploaded through the standard evidence ingestion service", "evidence": evidence_out(ev)}
