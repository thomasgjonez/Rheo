"""Signal-aware routing engine.

This is a time-dependent earliest-arrival search: a Dijkstra variant where
each state is (node, incoming_edge) rather than just (node), because the
wait you incur at an intersection depends on which approach you arrived
from (different approaches are green at different times). Edge costs are
non-negative and satisfy the FIFO property (leaving earlier never makes you
arrive later), which is what makes Dijkstra's ordering still correct here
even though the effective edge weight depends on arrival time.
"""

import heapq
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Tuple

from .graph import RoadNetwork
from .spat import SPaTProvider

Objective = Literal["fastest", "fewest_stops"]

State = Tuple[str, Optional[str]]  # (node_id, incoming_edge_id)


@dataclass
class RouteSegment:
    edge_id: str
    from_node: str
    to_node: str
    depart_time_s: float
    arrive_time_s: float
    wait_time_s: float
    travel_time_s: float
    stopped: bool


@dataclass
class RouteResult:
    found: bool
    total_time_s: float = 0.0
    total_distance_m: float = 0.0
    stops: int = 0
    segments: Optional[List[RouteSegment]] = None

    def __post_init__(self) -> None:
        if self.segments is None:
            self.segments = []


def find_route(
    network: RoadNetwork,
    spat: SPaTProvider,
    origin_node: str,
    destination_node: str,
    departure_time_s: float,
    objective: Objective = "fastest",
    avoid_highways: bool = False,
) -> RouteResult:
    if origin_node not in network.nodes or destination_node not in network.nodes:
        return RouteResult(found=False)

    def sort_key(time_s: float, stops: int) -> Tuple[float, float]:
        return (time_s, stops) if objective == "fastest" else (stops, time_s)

    start_state: State = (origin_node, None)
    best: Dict[State, Tuple[float, int]] = {start_state: (departure_time_s, 0)}
    prev: Dict[State, Tuple[Optional[State], Optional[RouteSegment]]] = {start_state: (None, None)}

    pq: List[Tuple[Tuple[float, float], State]] = [(sort_key(departure_time_s, 0), start_state)]
    visited = set()
    goal_state: Optional[State] = None

    while pq:
        _, state = heapq.heappop(pq)
        if state in visited:
            continue
        visited.add(state)

        node_id, in_edge = state
        time_s, stops = best[state]

        if node_id == destination_node:
            goal_state = state
            break

        wait = spat.wait_time_s(node_id, in_edge, time_s)
        depart_time = time_s + wait
        stopped_here = wait > 0.0

        for edge in network.outgoing_edges(node_id):
            if avoid_highways and edge.road_type == "highway":
                continue

            arrive = depart_time + edge.free_flow_travel_time_s
            new_stops = stops + (1 if stopped_here else 0)
            new_state: State = (edge.to_node, edge.id)
            candidate = (arrive, new_stops)

            if new_state not in best or sort_key(*candidate) < sort_key(*best[new_state]):
                best[new_state] = candidate
                seg = RouteSegment(
                    edge_id=edge.id,
                    from_node=node_id,
                    to_node=edge.to_node,
                    depart_time_s=depart_time,
                    arrive_time_s=arrive,
                    wait_time_s=wait if stopped_here else 0.0,
                    travel_time_s=edge.free_flow_travel_time_s,
                    stopped=stopped_here,
                )
                prev[new_state] = (state, seg)
                heapq.heappush(pq, (sort_key(*candidate), new_state))

    if goal_state is None:
        return RouteResult(found=False)

    segments: List[RouteSegment] = []
    state = goal_state
    while prev[state][0] is not None:
        parent, seg = prev[state]
        segments.append(seg)  # type: ignore[arg-type]
        state = parent  # type: ignore[assignment]
    segments.reverse()

    total_time = best[goal_state][0] - departure_time_s
    total_distance = sum(network.edges[s.edge_id].distance_m for s in segments)
    stops = sum(1 for s in segments if s.stopped)

    return RouteResult(
        found=True,
        total_time_s=total_time,
        total_distance_m=total_distance,
        stops=stops,
        segments=segments,
    )
