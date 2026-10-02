import time
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .graph import RoadNetwork
from .network_data import build_demo_network, build_demo_signals
from .routing import find_route

app = FastAPI(title="Signal-Aware Routing Prototype")

network: RoadNetwork = build_demo_network()
spat_provider = build_demo_signals(network)


class RouteRequest(BaseModel):
    origin: str
    destination: str
    departure_time: Optional[float] = None  # unix epoch seconds; defaults to now
    objective: Literal["fastest", "fewest_stops"] = "fastest"
    avoid_highways: bool = False


class SegmentOut(BaseModel):
    edge_id: str
    from_node: str
    to_node: str
    depart_time_s: float
    arrive_time_s: float
    wait_time_s: float
    travel_time_s: float
    stopped: bool


class RouteResponse(BaseModel):
    found: bool
    total_time_s: float
    total_distance_m: float
    stops: int
    path: List[str]
    segments: List[SegmentOut]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/network")
def get_network():
    return {
        "nodes": [{"id": n.id, "lat": n.lat, "lon": n.lon} for n in network.nodes.values()],
        "edges": [
            {"id": e.id, "from": e.from_node, "to": e.to_node, "distance_m": e.distance_m, "road_type": e.road_type}
            for e in network.edges.values()
        ],
    }


@app.post("/route", response_model=RouteResponse)
def route(req: RouteRequest):
    if req.origin not in network.nodes or req.destination not in network.nodes:
        raise HTTPException(status_code=404, detail="origin or destination node not found")

    departure_time = req.departure_time if req.departure_time is not None else time.time()

    result = find_route(
        network=network,
        spat=spat_provider,
        origin_node=req.origin,
        destination_node=req.destination,
        departure_time_s=departure_time,
        objective=req.objective,
        avoid_highways=req.avoid_highways,
    )

    if not result.found:
        raise HTTPException(status_code=404, detail="no route found")

    path = [req.origin] + [s.to_node for s in result.segments]

    return RouteResponse(
        found=True,
        total_time_s=result.total_time_s,
        total_distance_m=result.total_distance_m,
        stops=result.stops,
        path=path,
        segments=[SegmentOut(**s.__dict__) for s in result.segments],
    )
