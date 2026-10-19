"""Signal-aware routing.

`find_route` is a time-dependent earliest-arrival A* over directed edges. The search state is
the edge just traversed (not just the node), because the wait at a signal depends on which
approach you arrived by. Waits are non-negative and arriving earlier never makes you leave
later (FIFO), so the usual A* guarantees hold with a straight-line / top-speed lower bound.

`evaluate_path` replays a fixed list of edges against a provider - used to find what a
signal-blind route really costs once the signals are taken into account.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from .graph import RoadGraph
from .spat import SPaTProvider

STOP_THRESHOLD_S = 1.0  # waits shorter than this don't count as a stop


@dataclass
class SignalEvent:
    node: int
    arrive_epoch: float
    wait_s: float
    known: bool  # False when the provider had no data for this signal

    @property
    def stopped(self) -> bool:
        return self.wait_s >= STOP_THRESHOLD_S


@dataclass
class Route:
    edges: list[int]
    depart_epoch: float
    distance_m: float = 0.0
    drive_time_s: float = 0.0
    wait_s: float = 0.0
    events: list[SignalEvent] = field(default_factory=list)

    @property
    def total_time_s(self) -> float:
        return self.drive_time_s + self.wait_s

    @property
    def arrival_epoch(self) -> float:
        return self.depart_epoch + self.total_time_s

    @property
    def stops(self) -> int:
        return sum(1 for e in self.events if e.stopped)


def evaluate_path(graph: RoadGraph, provider: SPaTProvider, edges: list[int], depart_epoch: float) -> Route:
    route = Route(edges=list(edges), depart_epoch=depart_epoch)
    t = depart_epoch
    for i, e in enumerate(edges):
        if i > 0:
            node = graph.edge_to[edges[i - 1]]
            if graph.node_is_signal[node]:
                w = provider.wait_s(graph.signal_key(node), graph.edge_phase_group[edges[i - 1]], t)
                wait = w or 0.0
                route.events.append(SignalEvent(node, t, wait, w is not None))
                route.wait_s += wait
                t += wait
        t += graph.edge_travel_s[e]
        route.drive_time_s += graph.edge_travel_s[e]
        route.distance_m += graph.edge_length[e]
    return route


def find_route(
    graph: RoadGraph,
    provider: SPaTProvider,
    origin: int,
    dest: int,
    depart_epoch: float,
) -> Route | None:
    if origin == dest:
        return Route(edges=[], depart_epoch=depart_epoch)
    edges = _search(graph, provider, origin, dest, depart_epoch, allow_uturn=False)
    if edges is None:
        edges = _search(graph, provider, origin, dest, depart_epoch, allow_uturn=True)
    if edges is None:
        return None
    return evaluate_path(graph, provider, edges, depart_epoch)


def _search(
    graph: RoadGraph,
    provider: SPaTProvider,
    origin: int,
    dest: int,
    depart_epoch: float,
    allow_uturn: bool,
) -> list[int] | None:
    out_start, out_edges = graph.out_start, graph.out_edges
    edge_to, edge_from = graph.edge_to, graph.edge_from
    travel, is_signal, phase = graph.edge_travel_s, graph.node_is_signal, graph.edge_phase_group
    h = graph.heuristic_to(dest)

    best: dict[int, float] = {}
    prev: dict[int, int] = {}
    heap: list[tuple[float, int]] = []
    for k in range(out_start[origin], out_start[origin + 1]):
        f = out_edges[k]
        t = depart_epoch + travel[f]
        best[f] = t
        prev[f] = -1
        heapq.heappush(heap, (t + h[edge_to[f]], f))

    closed: set[int] = set()
    found = -1
    while heap:
        _, e = heapq.heappop(heap)
        if e in closed:
            continue
        closed.add(e)
        head = edge_to[e]
        t = best[e]
        if head == dest:
            found = e
            break
        if is_signal[head]:
            w = provider.wait_s(graph.signal_key(head), phase[e], t)
            if w:
                t += w
        back_to = edge_from[e]
        for k in range(out_start[head], out_start[head + 1]):
            f = out_edges[k]
            nxt = edge_to[f]
            if not allow_uturn and nxt == back_to:
                continue
            arrive = t + travel[f]
            if arrive < best.get(f, float("inf")):
                best[f] = arrive
                prev[f] = e
                heapq.heappush(heap, (arrive + h[nxt], f))

    if found < 0:
        return None
    path = []
    e = found
    while e != -1:
        path.append(e)
        e = prev[e]
    path.reverse()
    return path
