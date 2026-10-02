"""Builds a small demo road network + mock signal timings.

Replace this module with a real network loader (OSM extract, DOT road
inventory, etc.) and a real SPaTProvider to move from prototype to pilot.
"""

from .graph import Edge, Node, RoadNetwork
from .spat import MockSPaTProvider, SignalPlan


def build_demo_network(rows: int = 5, cols: int = 5, block_m: float = 150.0, speed_mps: float = 12.5) -> RoadNetwork:
    network = RoadNetwork()

    for r in range(rows):
        for c in range(cols):
            node_id = f"n{r}_{c}"
            network.add_node(Node(id=node_id, lat=37.77 + r * 0.001, lon=-122.42 + c * 0.001))

    def add_two_way(a: str, b: str, distance: float, speed: float, road_type: str = "arterial") -> None:
        network.add_edge(Edge(id=f"{a}->{b}", from_node=a, to_node=b, distance_m=distance, speed_limit_mps=speed, road_type=road_type))
        network.add_edge(Edge(id=f"{b}->{a}", from_node=b, to_node=a, distance_m=distance, speed_limit_mps=speed, road_type=road_type))

    for r in range(rows):
        for c in range(cols):
            node_id = f"n{r}_{c}"
            if c + 1 < cols:
                add_two_way(node_id, f"n{r}_{c + 1}", block_m, speed_mps)
            if r + 1 < rows:
                add_two_way(node_id, f"n{r + 1}_{c}", block_m, speed_mps)

    return network


def add_local_bypass(network: RoadNetwork, from_node: str, to_node: str, distance_m: float, speed_mps: float) -> None:
    """Adds an uncontrolled local-road shortcut directly between two nodes
    (e.g. a side street with a stop sign, not a signal). Used to demonstrate
    the router trading extra distance for avoiding a red light -- build_demo_signals
    skips signal assignment for "local" road_type edges, so this shortcut is
    always a free pass through, unlike the arterial route it bypasses.
    """
    network.add_edge(Edge(id=f"{from_node}=>{to_node}", from_node=from_node, to_node=to_node,
                           distance_m=distance_m, speed_limit_mps=speed_mps, road_type="local"))
    network.add_edge(Edge(id=f"{to_node}=>{from_node}", from_node=to_node, to_node=from_node,
                           distance_m=distance_m, speed_limit_mps=speed_mps, road_type="local"))


def build_demo_signals(
    network: RoadNetwork,
    cycle_length_s: float = 90.0,
    green_duration_s: float = 38.0,
    offset_step_s: float = 12.0,
) -> MockSPaTProvider:
    """Assigns a SignalPlan to every approach at every intersection.

    East-west approaches get an offset that increases with column index,
    simulating a synchronized "green wave" along the horizontal arterial.
    North-south approaches get the complementary (opposite) phase, as a
    real intersection would: only one axis can have the green at a time.
    """
    spat = MockSPaTProvider()

    incoming_by_node: dict = {}
    for edge in network.edges.values():
        incoming_by_node.setdefault(edge.to_node, []).append(edge)

    for node_id, incoming_edges in incoming_by_node.items():
        r, c = (int(x) for x in node_id[1:].split("_"))
        ew_offset = (c * offset_step_s) % cycle_length_s
        ns_offset = (ew_offset + cycle_length_s / 2) % cycle_length_s

        for edge in incoming_edges:
            if edge.road_type == "local":
                continue  # uncontrolled (e.g. stop-sign) approach, no signal to model

            from_r, _from_c = (int(x) for x in edge.from_node[1:].split("_"))
            is_horizontal_approach = from_r == r  # arriving from east or west
            offset = ew_offset if is_horizontal_approach else ns_offset

            start = offset
            end = offset + green_duration_s
            if end <= cycle_length_s:
                windows = ((start, end),)
            else:
                windows = ((start, cycle_length_s), (0.0, end - cycle_length_s))

            spat.set_plan(node_id, edge.id, SignalPlan(cycle_length_s=cycle_length_s, green_windows=windows))

    return spat
