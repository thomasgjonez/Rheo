from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Node:
    id: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Edge:
    id: str
    from_node: str
    to_node: str
    distance_m: float
    speed_limit_mps: float
    road_type: str = "arterial"  # "arterial" | "local" | "highway"

    @property
    def free_flow_travel_time_s(self) -> float:
        return self.distance_m / self.speed_limit_mps


class RoadNetwork:
    """Directed graph of intersections (nodes) and road segments (edges)."""

    def __init__(self) -> None:
        self.nodes: Dict[str, Node] = {}
        self.edges: Dict[str, Edge] = {}
        self._outgoing: Dict[str, List[str]] = {}

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node
        self._outgoing.setdefault(node.id, [])

    def add_edge(self, edge: Edge) -> None:
        self.edges[edge.id] = edge
        self._outgoing.setdefault(edge.from_node, []).append(edge.id)

    def outgoing_edges(self, node_id: str) -> List[Edge]:
        return [self.edges[eid] for eid in self._outgoing.get(node_id, [])]
