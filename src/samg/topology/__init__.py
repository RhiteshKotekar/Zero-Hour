"""Executable coordination graph construction and costing (owner: Dev A).

Public interface: ``build_graph``, ``eligible_topologies``, ``HopTable``,
``max_coordination_cost``, ``eligible_agents``, ``to_networkx``.
"""

from __future__ import annotations

import networkx as nx

from samg.domain import CoordinationGraph
from samg.topology.builder import eligible_agents
from samg.topology.costs import HopTable, PairRoute, max_coordination_cost
from samg.topology.templates import build_graph, eligible_topologies


def to_networkx(graph: CoordinationGraph) -> nx.MultiDiGraph:
    """Runtime NetworkX view of the full typed graph (for analysis and rendering)."""
    g = nx.MultiDiGraph(topology=graph.topology.value, graph_version=graph.graph_version)
    for node in graph.nodes:
        g.add_node(node.node_id, kind=node.kind.value, **node.attrs)
    for edge in graph.edges:
        g.add_edge(edge.source, edge.target, key=edge.kind.value, kind=edge.kind.value, **edge.attrs)
    return g


__all__ = [
    "HopTable",
    "PairRoute",
    "build_graph",
    "eligible_agents",
    "eligible_topologies",
    "max_coordination_cost",
    "to_networkx",
]
