from app.risk.graph import DependencyGraph, service_exposure_index
from app.services.graph_service import load_graph


def _graph() -> DependencyGraph:
    # SVC-A -> APP-1 -> DB-1 -> STORAGE-1
    #               -> IDP-1
    # SVC-B -> APP-2 -> IDP-1
    # cycle: DB-1 -> CACHE-1 -> DB-1
    return DependencyGraph(
        asset_deps={
            "APP-1": {"DB-1", "IDP-1"},
            "DB-1": {"STORAGE-1", "CACHE-1"},
            "CACHE-1": {"DB-1"},
            "APP-2": {"IDP-1"},
        },
        service_deps={"SVC-A": {"APP-1"}, "SVC-B": {"APP-2"}, "SVC-C": {"OTHER-1"}},
    )


def test_downstream_and_upstream_traversal_is_transitive_and_cycle_safe():
    g = _graph()
    assert g.downstream("APP-1") == {"DB-1", "IDP-1", "STORAGE-1", "CACHE-1"}
    assert g.upstream("STORAGE-1") == {"DB-1", "APP-1", "CACHE-1"}
    assert g.downstream("CACHE-1") == {"DB-1", "STORAGE-1"}


def test_impacted_services_follow_transitive_dependencies():
    g = _graph()
    assert g.impacted_services("IDP-1") == {"SVC-A", "SVC-B"}
    assert g.impacted_services("STORAGE-1") == {"SVC-A"}
    assert g.impacted_services("APP-2") == {"SVC-B"}
    assert g.impacted_services("UNRELATED") == set()


def test_service_distances_match_impacted_services():
    g = _graph()
    assert g.service_distances("IDP-1") == {"SVC-A": 2, "SVC-B": 2}
    assert g.service_distances("STORAGE-1") == {"SVC-A": 3}
    assert g.service_distances("APP-2") == {"SVC-B": 1}
    for asset in ("IDP-1", "STORAGE-1", "CACHE-1", "APP-1", "UNRELATED"):
        assert set(g.service_distances(asset)) == g.impacted_services(asset)


def test_paths_to_services_are_shortest_chains():
    paths = _graph().paths_to_services("STORAGE-1")
    assert paths == [["SVC-A", "APP-1", "DB-1", "STORAGE-1"]]
    idp_paths = _graph().paths_to_services("IDP-1")
    assert sorted(idp_paths) == [["SVC-A", "APP-1", "IDP-1"], ["SVC-B", "APP-2", "IDP-1"]]


def test_single_points_of_failure_require_criticality_and_no_redundancy():
    attrs = {
        "APP-1": {"criticality": "Critical", "has_redundancy": True},
        "DB-1": {"criticality": "Critical", "has_redundancy": False},
        "IDP-1": {"criticality": "Critical", "has_redundancy": False},
        "STORAGE-1": {"criticality": "Low", "has_redundancy": False},
        "CACHE-1": {"criticality": "High", "has_redundancy": True},
    }
    spofs = _graph().single_points_of_failure("SVC-A", attrs)
    # IDP-1 is shared by two services so it sorts first.
    assert [s["asset_id"] for s in spofs] == ["IDP-1", "DB-1"]
    assert spofs[0]["shared_by_services"] == 2


def test_service_exposure_index_formula():
    assert service_exposure_index([])["index"] == 0
    r = service_exposure_index([90, 60, 30, 10])
    # 0.7*90 + 0.3*mean(90,60,30)=63+18=81
    assert r["index"] == 81 and r["level"] == "Critical"
    assert r["inputs"] == [90, 60, 30]


def test_graph_loaded_from_database(db, world):
    ctx = load_graph(db)
    assert ctx.graph.impacted_services("IDP-CORE-001") == {"SVC-PAY", "SVC-OLB"}
    assert ctx.graph.impacted_services("DB-TXN-001") == {"SVC-PAY", "SVC-OLB"}
    assert ctx.graph.impacted_services("LAB-SRV-001") == set()
    ordered = ctx.impacted_services_sorted("IDP-CORE-001")
    assert all(s.tier == "Tier 1" for s in ordered)
