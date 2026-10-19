from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import geocode
from .graph import RoadGraph
from .routing import Route, evaluate_path, find_route
from .spat import SimulatedSPaTProvider, SPaTProvider, StubSPaTProvider

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GRAPH_PATH = REPO_ROOT / "data" / "sf_graph.npz"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
MAX_SNAP_M = 400.0  # farther than this from any road and the point is outside our coverage


class LatLon(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class RouteRequest(BaseModel):
    origin: LatLon
    destination: LatLon
    depart_epoch: float | None = Field(default=None, description="Unix seconds; defaults to now")
    spat_mode: Literal["simulated", "live"] = "simulated"


def route_payload(graph: RoadGraph, route: Route) -> dict:
    signals = [
        {
            "id": graph.signal_key(ev.node),
            "label": str(graph.node_label[ev.node]),
            "lat": float(graph.node_lat[ev.node]),
            "lon": float(graph.node_lon[ev.node]),
            "arrive_epoch": round(ev.arrive_epoch, 1),
            "wait_s": round(ev.wait_s, 1),
            "stopped": ev.stopped,
            "has_data": ev.known,
        }
        for ev in route.events
    ]
    return {
        "geometry": graph.path_geometry(route.edges),
        "distance_m": round(route.distance_m),
        "drive_time_s": round(route.drive_time_s, 1),
        "wait_s": round(route.wait_s, 1),
        "total_time_s": round(route.total_time_s, 1),
        "arrival_epoch": round(route.arrival_epoch, 1),
        "stops": route.stops,
        "signals_on_route": len(route.events),
        "signals_with_data": sum(1 for ev in route.events if ev.known),
        "signals": signals,
    }


def create_app(graph: RoadGraph | None = None) -> FastAPI:
    state: dict = {"graph": graph}
    providers: dict[str, SPaTProvider] = {"simulated": SimulatedSPaTProvider(), "live": StubSPaTProvider()}
    blind_provider = StubSPaTProvider()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if state["graph"] is None:
            path = Path(os.environ.get("RHEO_GRAPH_PATH", DEFAULT_GRAPH_PATH))
            if not path.exists():
                raise RuntimeError(
                    f"Road graph not found at {path}. Build it with scripts/build_graph.py (see README)."
                )
            state["graph"] = RoadGraph.load(path)
        yield

    app = FastAPI(title="Rheo API", version="0.1.0", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/meta")
    def meta():
        g: RoadGraph = state["graph"]
        return {
            "bbox": g.bbox,
            "nodes": g.n,
            "edges": g.m,
            "signals": g.signal_count,
            "attribution": g.meta.get("attribution", ""),
            "default_spat_mode": "simulated",
            "spat_modes": [
                {"id": mode, "label": p.label, "is_simulated": p.is_simulated, "connected": p.connected}
                for mode, p in providers.items()
            ],
        }

    @app.get("/api/geocode")
    def geocode_endpoint(q: str = Query(min_length=1, max_length=200)):
        g: RoadGraph = state["graph"]
        try:
            return {"results": geocode.search(q, tuple(g.bbox)), "error": None}
        except geocode.GeocodeError:
            return {"results": [], "error": "Address search is temporarily unavailable."}

    @app.post("/api/route")
    def route(req: RouteRequest):
        g: RoadGraph = state["graph"]
        provider = providers[req.spat_mode]
        depart = req.depart_epoch if req.depart_epoch is not None else time.time()

        o_node, o_dist = g.nearest_node(req.origin.lat, req.origin.lon)
        d_node, d_dist = g.nearest_node(req.destination.lat, req.destination.lon)
        if o_dist > MAX_SNAP_M:
            raise HTTPException(422, "The start point is too far from any road in the demo area (San Francisco and nearby). Try a spot closer to a street.")
        if d_dist > MAX_SNAP_M:
            raise HTTPException(422, "The destination is too far from any road in the demo area (San Francisco and nearby). Try a spot closer to a street.")
        if o_node == d_node:
            raise HTTPException(422, "Those two points are too close together to route between.")

        # Signal-blind baseline: the route a router with no signal data would pick, then replayed
        # against the same signals to see what following it really costs.
        blind_pick = find_route(g, blind_provider, o_node, d_node, depart)
        if blind_pick is None:
            raise HTTPException(404, "No drivable route between those points.")
        blind = evaluate_path(g, provider, blind_pick.edges, depart)
        aware = blind if not provider.connected else find_route(g, provider, o_node, d_node, depart)
        assert aware is not None

        def snapped(node: int, requested: LatLon, dist: float) -> dict:
            return {
                "requested": {"lat": requested.lat, "lon": requested.lon},
                "snapped": {"lat": float(g.node_lat[node]), "lon": float(g.node_lon[node])},
                "snap_distance_m": round(dist),
            }

        return {
            "depart_epoch": depart,
            "spat": {
                "mode": req.spat_mode,
                "label": provider.label,
                "is_simulated": provider.is_simulated,
                "connected": provider.connected,
            },
            "origin": snapped(o_node, req.origin, o_dist),
            "destination": snapped(d_node, req.destination, d_dist),
            "blind": route_payload(g, blind),
            "aware": route_payload(g, aware),
            "comparison": {
                "same_route": blind.edges == aware.edges,
                "time_saved_s": round(blind.total_time_s - aware.total_time_s, 1),
                "wait_saved_s": round(blind.wait_s - aware.wait_s, 1),
                "stops_avoided": blind.stops - aware.stops,
            },
        }

    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

    return app


app = create_app()
