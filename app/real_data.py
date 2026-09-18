"""Builds a RoadNetwork from real, cleaned intersection data (OpenStreetMap
node coordinates for actual signalized intersections along a real street),
rather than the synthetic demo grid in network_data.py.

Signal *timing* (cycle length, offsets, splits) is a separate matter: that
data is not public for this corridor -- see the market-validation research
in README.md for why (it's held by the traffic-signal vendors/agencies, not
published). So real_data.py is honest about the split: geometry and
distances below are real OSM data; the SignalPlan objects are a labeled
assumption, not a claim about actual light timing on Market Street.
"""

import json
import math
from pathlib import Path
from typing import List

from .graph import Edge, Node, RoadNetwork
from .spat import MockSPaTProvider, SignalPlan

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "market_street_signals.json"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_intersections() -> List[dict]:
    with open(DATA_PATH) as f:
        return json.load(f)


def build_market_street_network(speed_mps: float = 11.2) -> RoadNetwork:
    """speed_mps default ~25mph, San Francisco's default urban arterial limit."""
    intersections = load_intersections()
    network = RoadNetwork()

    node_ids = []
    for i, x in enumerate(intersections):
        node_id = f"m{i}"
        network.add_node(Node(id=node_id, lat=x["lat"], lon=x["lon"]))
        node_ids.append(node_id)

    for a, b, xa, xb in zip(node_ids, node_ids[1:], intersections, intersections[1:]):
        distance = haversine_m(xa["lat"], xa["lon"], xb["lat"], xb["lon"])
        network.add_edge(Edge(id=f"{a}->{b}", from_node=a, to_node=b, distance_m=distance, speed_limit_mps=speed_mps))
        network.add_edge(Edge(id=f"{b}->{a}", from_node=b, to_node=a, distance_m=distance, speed_limit_mps=speed_mps))

    return network


def build_market_street_signals(
    network: RoadNetwork,
    cycle_length_s: float = 90.0,
    green_duration_s: float = 35.0,
    offset_step_s: float = 10.0,
) -> MockSPaTProvider:
    """ASSUMED timing: a simple progressive offset per intersection (a green
    wave), not real ATSPM/SPaT data -- that's not publicly available for
    this corridor. This is here so the real geometry can be run through the
    signal-aware router at all; treat the *positions/distances* as real and
    the *timing* as illustrative.
    """
    spat = MockSPaTProvider()
    incoming_by_node: dict = {}
    for edge in network.edges.values():
        incoming_by_node.setdefault(edge.to_node, []).append(edge)

    for i, (node_id, incoming_edges) in enumerate(incoming_by_node.items()):
        offset = (i * offset_step_s) % cycle_length_s
        start, end = offset, offset + green_duration_s
        windows = ((start, end),) if end <= cycle_length_s else ((start, cycle_length_s), (0.0, end - cycle_length_s))
        for edge in incoming_edges:
            spat.set_plan(node_id, edge.id, SignalPlan(cycle_length_s=cycle_length_s, green_windows=windows))

    return spat
