"""Business service dependency graph traversal (pure, cycle-safe)."""

from collections import deque
from dataclasses import dataclass, field


@dataclass
class DependencyGraph:
    # asset -> assets it depends on
    asset_deps: dict[str, set[str]] = field(default_factory=dict)
    # service -> assets it directly depends on
    service_deps: dict[str, set[str]] = field(default_factory=dict)

    def __post_init__(self):
        self._reverse: dict[str, set[str]] = {}
        for src, targets in self.asset_deps.items():
            for t in targets:
                self._reverse.setdefault(t, set()).add(src)

    def downstream(self, asset_id: str) -> set[str]:
        """All assets that `asset_id` depends on, transitively."""
        return self._walk(asset_id, self.asset_deps)

    def upstream(self, asset_id: str) -> set[str]:
        """All assets that depend on `asset_id`, transitively."""
        return self._walk(asset_id, self._reverse)

    @staticmethod
    def _walk(start: str, edges: dict[str, set[str]]) -> set[str]:
        seen: set[str] = set()
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for nxt in edges.get(node, ()):
                if nxt not in seen and nxt != start:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    def service_closure(self, service_id: str) -> set[str]:
        """Every asset a service depends on, directly or transitively."""
        result: set[str] = set()
        for a in self.service_deps.get(service_id, ()):
            result.add(a)
            result |= self.downstream(a)
        return result

    def impacted_services(self, asset_id: str) -> set[str]:
        """Services whose dependency closure includes `asset_id`."""
        affected = self.upstream(asset_id) | {asset_id}
        return {s for s, direct in self.service_deps.items() if direct & affected}

    def service_distances(self, asset_id: str) -> dict[str, int]:
        """Hop count from each impacted service to `asset_id` (1 = direct dependency)."""
        dist: dict[str, int] = {asset_id: 0}
        queue = deque([asset_id])
        while queue:
            node = queue.popleft()
            for up in self._reverse.get(node, ()):
                if up not in dist:
                    dist[up] = dist[node] + 1
                    queue.append(up)
        result: dict[str, int] = {}
        for service_id, direct in self.service_deps.items():
            hops = [dist[a] for a in direct if a in dist]
            if hops:
                result[service_id] = min(hops) + 1
        return result

    def paths_to_services(self, asset_id: str, max_paths: int = 50) -> list[list[str]]:
        """Shortest dependency chains from each impacted service down to `asset_id`.

        Each path is ``[service_id, asset_1, ..., asset_id]``.
        """
        paths: list[list[str]] = []
        # BFS upward from the asset recording parents to reconstruct shortest chains.
        parent: dict[str, str | None] = {asset_id: None}
        queue = deque([asset_id])
        order = [asset_id]
        while queue:
            node = queue.popleft()
            for up in sorted(self._reverse.get(node, ())):
                if up not in parent:
                    parent[up] = node
                    queue.append(up)
                    order.append(up)
        for service_id in sorted(self.service_deps):
            direct = self.service_deps[service_id]
            candidates = [a for a in order if a in direct]
            if not candidates:
                continue
            entry = candidates[0]
            chain = [entry]
            while parent[chain[-1]] is not None:
                chain.append(parent[chain[-1]])
            paths.append([service_id, *chain])
            if len(paths) >= max_paths:
                break
        return paths

    def service_dependents_count(self) -> dict[str, int]:
        """How many services rely on each asset (concentration)."""
        counts: dict[str, int] = {}
        for s in self.service_deps:
            for a in self.service_closure(s):
                counts[a] = counts.get(a, 0) + 1
        return counts

    def single_points_of_failure(self, service_id: str, asset_attrs: dict[str, dict]) -> list[dict]:
        """Assets in the service's dependency closure with no documented redundancy.

        Only Critical/High assets are reported, ordered by how many services share the dependency.
        """
        counts = self.service_dependents_count()
        spofs = []
        for a in sorted(self.service_closure(service_id)):
            attrs = asset_attrs.get(a, {})
            if attrs.get("has_redundancy"):
                continue
            if attrs.get("criticality") not in ("Critical", "High"):
                continue
            spofs.append({"asset_id": a, "shared_by_services": counts.get(a, 1), **attrs})
        spofs.sort(key=lambda x: (-x["shared_by_services"], x["asset_id"]))
        return spofs


def service_exposure_index(open_scores: list[int]) -> dict:
    """Transparent aggregate indicator of potential exposure for a business service.

    index = 0.7 * highest open finding score + 0.3 * mean of top-3 open finding scores
    """
    if not open_scores:
        return {"index": 0, "level": "None", "formula": "No open findings in dependency path", "inputs": []}
    top = sorted(open_scores, reverse=True)
    top3 = top[:3]
    index = round(0.7 * top[0] + 0.3 * (sum(top3) / len(top3)))
    level = "Critical" if index >= 80 else "High" if index >= 60 else "Medium" if index >= 40 else "Low"
    return {
        "index": index,
        "level": level,
        "formula": "0.7 x highest open finding score + 0.3 x mean(top 3 open finding scores)",
        "inputs": top3,
    }
