from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.serializers import assessment_out, finding_out, paginate_params
from app.core import permissions as P
from app.core.audit import record_audit
from app.core.database import get_db
from app.core.deps import require
from app.core.rate_limit import client_ip
from app.models import (
    Asset,
    AssetDependency,
    BusinessService,
    ControlAssessment,
    ControlAssetScope,
    Finding,
    ServiceAssetDependency,
    User,
)
from app.schemas.common import Page
from app.schemas.entities import AssetCreate, AssetListItem, AssetOut, AssetUpdate
from app.services.graph_service import load_graph

router = APIRouter(prefix="/assets", tags=["Technology Assets"])

SORTABLE = {"id": Asset.id, "name": Asset.name, "criticality": Asset.criticality, "asset_type": Asset.asset_type,
            "last_assessed_at": Asset.last_assessed_at}


@router.get("", response_model=Page[AssetListItem], dependencies=[Depends(require(P.READ))])
def list_assets(
    q: str | None = Query(None, max_length=100),
    asset_type: str | None = None,
    criticality: str | None = None,
    environment: str | None = None,
    service_id: str | None = None,
    internet_exposed: bool | None = None,
    sort: str = "id",
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
):
    page, page_size = paginate_params(page, page_size)
    stmt = select(Asset)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Asset.id.ilike(like), Asset.name.ilike(like), Asset.platform.ilike(like),
                              Asset.technical_owner.ilike(like), Asset.business_owner.ilike(like)))
    if asset_type:
        stmt = stmt.where(Asset.asset_type == asset_type)
    if criticality:
        stmt = stmt.where(Asset.criticality == criticality)
    if environment:
        stmt = stmt.where(Asset.environment == environment)
    if internet_exposed is not None:
        stmt = stmt.where(Asset.internet_exposed.is_(internet_exposed))
    if service_id:
        gctx = load_graph(db)
        ids = gctx.graph.service_closure(service_id)
        stmt = stmt.where(Asset.id.in_(ids or {"__none__"}))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    desc = sort.startswith("-")
    col = SORTABLE.get(sort.lstrip("-"), Asset.id)
    stmt = stmt.order_by(col.desc() if desc else col.asc(), Asset.id).offset((page - 1) * page_size).limit(page_size)
    assets = db.scalars(stmt).all()
    ids = [a.id for a in assets]
    svc_map: dict[str, list[str]] = {}
    for aid, name in db.execute(
        select(ServiceAssetDependency.asset_id, BusinessService.name).join(BusinessService)
        .where(ServiceAssetDependency.asset_id.in_(ids))
    ):
        svc_map.setdefault(aid, []).append(name)
    open_counts = dict(db.execute(
        select(Finding.asset_id, func.count()).where(Finding.asset_id.in_(ids), Finding.status != "Resolved")
        .group_by(Finding.asset_id)).all())
    items = [
        AssetListItem(**AssetOut.model_validate(a).model_dump(), services=sorted(svc_map.get(a.id, [])),
                      open_findings=open_counts.get(a.id, 0))
        for a in assets
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{asset_id}", dependencies=[Depends(require(P.READ))])
def get_asset(asset_id: str, db: Session = Depends(get_db)):
    a = db.get(Asset, asset_id)
    if a is None:
        raise HTTPException(404, "Asset not found")
    gctx = load_graph(db)
    direct_services = [s for s in db.scalars(
        select(BusinessService).join(ServiceAssetDependency).where(ServiceAssetDependency.asset_id == asset_id))]
    impacted = gctx.impacted_services_sorted(asset_id)
    depends_on = db.execute(select(AssetDependency.depends_on_asset_id, Asset.name, Asset.asset_type, AssetDependency.dependency_type)
                            .join(Asset, Asset.id == AssetDependency.depends_on_asset_id)
                            .where(AssetDependency.asset_id == asset_id)).all()
    dependents = db.execute(select(AssetDependency.asset_id, Asset.name, Asset.asset_type, AssetDependency.dependency_type)
                            .join(Asset, Asset.id == AssetDependency.asset_id)
                            .where(AssetDependency.depends_on_asset_id == asset_id)).all()
    scopes = db.scalars(select(ControlAssetScope).where(ControlAssetScope.asset_id == asset_id)).all()
    controls = []
    for s in scopes:
        latest = db.get(ControlAssessment, s.latest_assessment_id) if s.latest_assessment_id else None
        controls.append({
            "control_id": s.control_id, "control_name": s.control.name, "domain": s.control.domain,
            "status": s.current_status, "last_assessed_at": s.last_assessed_at,
            "latest_assessment": assessment_out(latest) if latest else None,
        })
    findings = db.scalars(select(Finding).where(Finding.asset_id == asset_id).order_by(Finding.detected_at.desc())).all()
    history = db.scalars(select(ControlAssessment).where(ControlAssessment.asset_id == asset_id)
                         .order_by(ControlAssessment.assessed_at.desc(), ControlAssessment.id.desc()).limit(60)).all()
    return {
        "asset": AssetOut.model_validate(a),
        "direct_services": [{"id": s.id, "name": s.name, "tier": s.tier} for s in direct_services],
        "impacted_services": [{"id": s.id, "name": s.name, "tier": s.tier} for s in impacted],
        "depends_on": [{"id": r[0], "name": r[1], "asset_type": r[2], "dependency_type": r[3]} for r in depends_on],
        "dependents": [{"id": r[0], "name": r[1], "asset_type": r[2], "dependency_type": r[3]} for r in dependents],
        "controls": controls,
        "findings": [finding_out(f) for f in findings],
        "assessment_history": [assessment_out(h) for h in history],
    }


def _sync_services(db: Session, asset_id: str, service_ids: list[str]) -> None:
    for sid in service_ids:
        if db.get(BusinessService, sid) is None:
            raise HTTPException(422, f"Unknown business service '{sid}'")
    existing = {l.service_id: l for l in db.scalars(select(ServiceAssetDependency).where(ServiceAssetDependency.asset_id == asset_id))}
    for sid, link in existing.items():
        if sid not in service_ids:
            db.delete(link)
    for sid in service_ids:
        if sid not in existing:
            db.add(ServiceAssetDependency(service_id=sid, asset_id=asset_id, role="core"))


@router.post("", response_model=AssetOut, status_code=201)
def create_asset(body: AssetCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require(P.ASSETS_WRITE))):
    if db.get(Asset, body.id) is not None:
        raise HTTPException(409, f"Asset '{body.id}' already exists")
    data = body.model_dump(exclude={"service_ids"})
    asset = Asset(**data)
    db.add(asset)
    db.flush()
    _sync_services(db, asset.id, body.service_ids)
    record_audit(db, "asset.create", actor=user, entity_type="asset", entity_id=asset.id, details=data, ip_address=client_ip(request))
    db.commit()
    return asset


@router.patch("/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: str, body: AssetUpdate, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require(P.ASSETS_WRITE))):
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "Asset not found")
    changes = body.model_dump(exclude_unset=True, exclude={"service_ids"})
    before = {k: getattr(asset, k) for k in changes}
    for k, v in changes.items():
        if v is not None:
            setattr(asset, k, v)
    if body.service_ids is not None:
        _sync_services(db, asset.id, body.service_ids)
    record_audit(db, "asset.update", actor=user, entity_type="asset", entity_id=asset.id,
                 details={"before": {k: str(v) for k, v in before.items()}, "after": {k: str(v) for k, v in changes.items()},
                          "service_ids": body.service_ids},
                 ip_address=client_ip(request))
    db.commit()
    return asset
