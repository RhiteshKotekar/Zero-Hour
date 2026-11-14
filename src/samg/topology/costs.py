"""Graph-derived coordination distances and costs (brief §5.4).

The same rule applies to every topology: a handoff between different agents
costs ``h0 + h1 * hops`` along the shortest permitted coordination path; with
no permitted path (or a path longer than ``max_path_hops``) the pair is
infeasible. Topologies differ only in which links exist.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from samg.domain import CoordinationGraph, TopologyCostConfig


@dataclass(frozen=True)
class PairRoute:
    hops: int
    path: tuple[str, ...]
    cost: float
    delay: float


class HopTable:
    """All-pairs shortest coordination paths between agents (deterministic BFS)."""

    def __init__(self, graph: CoordinationGraph, costs: TopologyCostConfig) -> None:
        self.costs = costs
        self.agents = graph.agent_ids()
        self.links = graph.coordination_links()
        adjacency: dict[str, list[str]] = {a: [] for a in self.agents}
        for a, b in self.links:
            adjacency[a].append(b)
            adjacency[b].append(a)
        self._adjacency = {a: sorted(ns) for a, ns in adjacency.items()}
        self._paths: dict[str, dict[str, tuple[str, ...]]] = {a: self._bfs(a) for a in self.agents}

    def _bfs(self, source: str) -> dict[str, tuple[str, ...]]:
        paths = {source: (source,)}
        queue = deque([source])
        while queue:
            current = queue.popleft()
            for nxt in self._adjacency[current]:
                if nxt not in paths:
                    paths[nxt] = paths[current] + (nxt,)
                    queue.append(nxt)
        return paths

    def hops(self, a: str, b: str) -> int | None:
        path = self._paths.get(a, {}).get(b)
        return None if path is None else len(path) - 1

    def route(self, a: str, b: str) -> PairRoute | None:
        """Route for a handoff ``a -> b``, or ``None`` if no permitted path exists."""
        path = self._paths.get(a, {}).get(b)
        if path is None:
            return None
        hops = len(path) - 1
        if hops > self.costs.max_path_hops:
            return None
        return PairRoute(hops=hops, path=path, cost=self.costs.handoff_cost(hops),
                         delay=hops * self.costs.handoff_delay_per_hop)

    def link_maintenance_cost(self) -> float:
        return self.costs.link_cost * len(self.links)


def max_coordination_cost(n_dependencies: int, n_agents: int, costs: TopologyCostConfig) -> float:
    """Upper bound used to normalise H to [0, 1]: every dependency at max hops plus a full mesh of links."""
    full_mesh = n_agents * (n_agents - 1) / 2
    bound = n_dependencies * costs.handoff_cost(costs.max_path_hops) + costs.link_cost * full_mesh
    return bound if bound > 0 else 1.0
