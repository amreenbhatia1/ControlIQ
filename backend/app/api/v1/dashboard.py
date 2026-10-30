from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.serializers import finding_out
from app.core import permissions as P
from app.core.database import get_db
from app.core.deps import require
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"], dependencies=[Depends(require(P.READ))])


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    run = dashboard_service.last_run(db)
    return {
        "kpis": dashboard_service.kpis(db),
        "severity_distribution": dashboard_service.severity_distribution(db),
        "domain_distribution": dashboard_service.domain_distribution(db),
        "services_at_risk": dashboard_service.services_at_risk(db, limit=6),
        "critical_attention": [finding_out(f) for f in dashboard_service.critical_attention(db, 5)],
        "last_assessment": None
        if run is None
        else {"id": run.id, "ref": run.ref, "evaluated_at": run.evaluated_at, "trigger": run.trigger,
              "triggered_by": run.triggered_by.full_name if run.triggered_by else "Scheduler"},
    }


@router.get("/trend")
def trend(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    return {"days": days, "points": dashboard_service.trend(db, days)}
