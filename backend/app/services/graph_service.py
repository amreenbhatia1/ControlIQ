from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, AssetDependency, BusinessService, ServiceAssetDependency
from app.risk.graph import DependencyGraph

TIER_ORDER = {"Tier 1": 0, "Tier 2": 1, "Tier 3": 2}


@dataclass
class GraphContext:
    graph: DependencyGraph
    services: dict[str, BusinessService]
    asset_attrs: dict[str, dict]

    def impacted_services_sorted(self, asset_id: str) -> list[BusinessService]:
        dist = self.graph.service_distances(asset_id)
        return sorted((self.services[s] for s in dist), key=lambda s: (TIER_ORDER[s.tier], dist[s.id], s.name))


def load_graph(db: Session) -> GraphContext:
    asset_deps: dict[str, set[str]] = {}
    for a, b in db.execute(select(AssetDependency.asset_id, AssetDependency.depends_on_asset_id)):
        asset_deps.setdefault(a, set()).add(b)
    service_deps: dict[str, set[str]] = {}
    for s, a in db.execute(select(ServiceAssetDependency.service_id, ServiceAssetDependency.asset_id)):
        service_deps.setdefault(s, set()).add(a)
    services = {s.id: s for s in db.scalars(select(BusinessService))}
    for sid in services:
        service_deps.setdefault(sid, set())
    attrs = {
        row.id: {
            "name": row.name,
            "asset_type": row.asset_type,
            "criticality": row.criticality,
            "has_redundancy": row.has_redundancy,
            "internet_exposed": row.internet_exposed,
        }
        for row in db.execute(
            select(
                Asset.id, Asset.name, Asset.asset_type, Asset.criticality, Asset.has_redundancy, Asset.internet_exposed
            )
        )
    }
    return GraphContext(DependencyGraph(asset_deps, service_deps), services, attrs)
