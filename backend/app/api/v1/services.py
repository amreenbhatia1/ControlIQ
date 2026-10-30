from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serializers import finding_out
from app.core import permissions as P
from app.core.database import get_db
from app.core.deps import require
from app.models import Asset, AssetDependency, BusinessService, ControlAssetScope, Finding, ServiceAssetDependency
from app.models.enums import UNRESOLVED_FINDING_STATUSES
from app.risk.graph import service_exposure_index
from app.schemas.entities import ServiceOut
from app.services.graph_service import load_graph

router = APIRouter(prefix="/business-services", tags=["Business Services"], dependencies=[Depends(require(P.READ))])

STATUS_RANK = {"Ineffective": 3, "Needs Review": 2, "Effective": 1, "Not Assessed": 0}


def _asset_status_map(db: Session) -> dict[str, str]:
    worst: dict[str, str] = {}
    for aid, status in db.execute(select(ControlAssetScope.asset_id, ControlAssetScope.current_status)):
        current = worst.get(aid)
        if current is None or STATUS_RANK[status] > STATUS_RANK[current]:
            worst[aid] = status
    return worst


def _active_findings_by_asset(db: Session) -> dict[str, list[Finding]]:
    out: dict[str, list[Finding]] = {}
    for f in db.scalars(select(Finding).where(Finding.status != "Resolved")):
        out.setdefault(f.asset_id, []).append(f)
    return out


@router.get("")
def list_services(db: Session = Depends(get_db)):
    gctx = load_graph(db)
    findings = [f for f in db.scalars(select(Finding).where(Finding.status.in_(UNRESOLVED_FINDING_STATUSES)))]
    out = []
    for s in sorted(gctx.services.values(), key=lambda s: (s.tier, s.name)):
        related = [f for f in findings if s.id in (f.impacted_service_ids or [])]
        exposure = service_exposure_index([f.risk_score for f in related])
        closure = gctx.graph.service_closure(s.id)
        out.append({
            **ServiceOut.model_validate(s).model_dump(),
            "asset_count": len(closure),
            "direct_asset_count": len(gctx.graph.service_deps.get(s.id, ())),
            "unresolved_findings": len(related),
            "critical_findings": sum(1 for f in related if f.severity == "Critical"),
            "exposure": exposure,
            "spof_count": len(gctx.graph.single_points_of_failure(s.id, gctx.asset_attrs)),
        })
    return out


@router.get("/graph")
def graph(service_id: str | None = None, asset_id: str | None = None, include_hosts: bool = False,
          db: Session = Depends(get_db)):
    gctx = load_graph(db)
    g = gctx.graph
    status = _asset_status_map(db)
    by_asset = _active_findings_by_asset(db)
    counts = g.service_dependents_count()
    edges_all = db.execute(select(AssetDependency.asset_id, AssetDependency.depends_on_asset_id, AssetDependency.dependency_type)).all()

    focus = None
    if asset_id:
        if asset_id not in gctx.asset_attrs:
            raise HTTPException(404, "Asset not found")
        upstream, downstream = g.upstream(asset_id), g.downstream(asset_id)
        impacted = g.impacted_services(asset_id)
        assets = {asset_id} | upstream | downstream
        services = set(impacted)
        related = []
        for aid in sorted({asset_id} | downstream):
            for f in by_asset.get(aid, []):
                related.append(finding_out(f))
        paths = g.paths_to_services(asset_id)
        exposure = service_exposure_index([f.risk_score for f in by_asset.get(asset_id, []) if f.status in UNRESOLVED_FINDING_STATUSES])
        focus = {
            "asset_id": asset_id,
            "asset_name": gctx.asset_attrs[asset_id]["name"],
            "upstream": sorted(upstream),
            "downstream": sorted(downstream),
            "impacted_services": [{"id": s.id, "name": s.name, "tier": s.tier} for s in gctx.impacted_services_sorted(asset_id)],
            "paths": paths,
            "related_findings": related,
            "asset_exposure": exposure,
            "is_spof": not gctx.asset_attrs[asset_id]["has_redundancy"] and gctx.asset_attrs[asset_id]["criticality"] in ("Critical", "High"),
            "shared_by_services": counts.get(asset_id, 0),
        }
    elif service_id:
        if service_id not in gctx.services:
            raise HTTPException(404, "Business service not found")
        services = {service_id}
        assets = g.service_closure(service_id)
    else:
        services = set(gctx.services)
        assets = set()
        for sid in services:
            assets |= g.service_closure(sid)

    if not include_hosts and not asset_id:
        hosted = {b for a, b, t in edges_all if t == "hosted on"}
        assets = {a for a in assets if a not in hosted}

    nodes = []
    for sid in sorted(services):
        s = gctx.services[sid]
        svc_findings = [f for fs in by_asset.values() for f in fs
                        if sid in (f.impacted_service_ids or []) and f.status in UNRESOLVED_FINDING_STATUSES]
        exp = service_exposure_index([f.risk_score for f in svc_findings])
        nodes.append({"id": sid, "kind": "service", "label": s.name, "sublabel": s.tier, "tier": s.tier,
                      "open_findings": len(svc_findings), "exposure_index": exp["index"], "exposure_level": exp["level"]})
    spof_ids = set()
    for sid in services:
        spof_ids |= {x["asset_id"] for x in g.single_points_of_failure(sid, gctx.asset_attrs)}
    for aid in sorted(assets):
        attrs = gctx.asset_attrs[aid]
        fs = [f for f in by_asset.get(aid, []) if f.status in UNRESOLVED_FINDING_STATUSES]
        nodes.append({
            "id": aid, "kind": "asset", "label": attrs["name"], "sublabel": aid, "asset_type": attrs["asset_type"],
            "criticality": attrs["criticality"], "internet_exposed": attrs["internet_exposed"],
            "has_redundancy": attrs["has_redundancy"], "control_status": status.get(aid, "Not Assessed"),
            "open_findings": len(fs), "max_risk_score": max((f.risk_score for f in fs), default=0),
            "spof": aid in spof_ids, "shared_by_services": counts.get(aid, 0),
        })
    edges = []
    for sid in services:
        for aid in g.service_deps.get(sid, ()):
            if aid in assets:
                edges.append({"id": f"{sid}->{aid}", "source": sid, "target": aid, "kind": "service", "dependency_type": "depends on"})
    for a, b, t in edges_all:
        if a in assets and b in assets:
            edges.append({"id": f"{a}->{b}", "source": a, "target": b, "kind": "asset", "dependency_type": t})
    return {"nodes": nodes, "edges": edges, "focus": focus}


@router.get("/{service_id}")
def get_service(service_id: str, db: Session = Depends(get_db)):
    s = db.get(BusinessService, service_id)
    if s is None:
        raise HTTPException(404, "Business service not found")
    gctx = load_graph(db)
    closure = gctx.graph.service_closure(service_id)
    status = _asset_status_map(db)
    findings = [f for f in db.scalars(select(Finding).where(Finding.status != "Resolved").order_by(Finding.risk_score.desc()))
                if service_id in (f.impacted_service_ids or [])]
    direct = set(db.scalars(select(ServiceAssetDependency.asset_id).where(ServiceAssetDependency.service_id == service_id)))
    assets = db.scalars(select(Asset).where(Asset.id.in_(closure or {"__none__"})).order_by(Asset.criticality, Asset.id)).all()
    unresolved = [f for f in findings if f.status in UNRESOLVED_FINDING_STATUSES]
    return {
        "service": ServiceOut.model_validate(s),
        "exposure": service_exposure_index([f.risk_score for f in unresolved]),
        "assets": [{"id": a.id, "name": a.name, "asset_type": a.asset_type, "criticality": a.criticality,
                    "direct": a.id in direct, "control_status": status.get(a.id, "Not Assessed"),
                    "has_redundancy": a.has_redundancy, "internet_exposed": a.internet_exposed} for a in assets],
        "findings": [finding_out(f) for f in findings],
        "single_points_of_failure": gctx.graph.single_points_of_failure(service_id, gctx.asset_attrs),
    }
