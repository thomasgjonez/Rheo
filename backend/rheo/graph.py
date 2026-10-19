"""In-memory road graph used by the router.

Nodes are intersections/endpoints/signals; edges are directed drivable segments.
Hot-loop attributes are plain Python lists (numpy scalar access is slow in pure-Python
search loops); array-shaped data (geometry, KD-tree) stays in numpy.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Mapping

import numpy as np
from scipy.spatial import cKDTree

FREEWAY_CLASSES = (0, 1)  # motorway, motorway_link (indices from scripts/build_graph.py)
M_PER_DEG_LAT = 110_540.0
M_PER_DEG_LON_EQ = 111_320.0


class RoadGraph:
    def __init__(self, data: Mapping[str, np.ndarray]):
        self.meta = json.loads(str(data["meta"])) if "meta" in data else {}
        self.node_osm_id = np.asarray(data["node_osm_id"])
        self.node_lat = np.asarray(data["node_lat"], dtype=np.float64)
        self.node_lon = np.asarray(data["node_lon"], dtype=np.float64)
        self.node_label = np.asarray(data["node_label"])
        self.node_is_signal: list[bool] = np.asarray(data["node_is_signal"]).tolist()
        self.n = len(self.node_lat)

        edge_from = np.asarray(data["edge_from"], dtype=np.int64)
        edge_to = np.asarray(data["edge_to"], dtype=np.int64)
        length = np.asarray(data["edge_length_m"], dtype=np.float64)
        speed = np.asarray(data["edge_speed_mps"], dtype=np.float64)
        self.m = len(edge_from)
        self.edge_from: list[int] = edge_from.tolist()
        self.edge_to: list[int] = edge_to.tolist()
        self.edge_length: list[float] = length.tolist()
        self.edge_travel_s: list[float] = (length / speed).tolist()
        self.max_speed_mps = float(speed.max())
        self.edge_class = np.asarray(data["edge_class"])

        # Signals are grouped into two approach groups by heading: 0 = roughly north/south, 1 = east/west.
        axis = np.asarray(data["edge_end_bearing"], dtype=np.float64) % 180.0
        self.edge_phase_group: list[int] = np.where((axis < 45.0) | (axis >= 135.0), 0, 1).tolist()

        order = np.argsort(edge_from, kind="stable")
        self.out_edges: list[int] = order.tolist()
        self.out_start: list[int] = np.searchsorted(edge_from[order], np.arange(self.n + 1)).tolist()

        self.geom_offsets = np.asarray(data["geom_offsets"])
        self.geom_coords = np.asarray(data["geom_coords"])

        lat0 = float(self.node_lat.mean())
        self._lat0, self._lon0 = lat0, float(self.node_lon.mean())
        self._cos_lat0 = math.cos(math.radians(lat0))
        px, py = self._project(self.node_lat, self.node_lon)
        self._px, self._py = px, py

        surface = np.zeros(self.n, dtype=bool)
        non_freeway = ~np.isin(self.edge_class, FREEWAY_CLASSES)
        surface[edge_from[non_freeway]] = True
        surface[edge_to[non_freeway]] = True
        self._surface_ids = np.nonzero(surface)[0]
        self._tree = cKDTree(np.column_stack([px[self._surface_ids], py[self._surface_ids]]))

    @classmethod
    def load(cls, path: str | Path) -> "RoadGraph":
        with np.load(path, allow_pickle=False) as z:
            return cls({k: z[k] for k in z.files})

    def _project(self, lat, lon):
        x = (np.asarray(lon) - self._lon0) * self._cos_lat0 * M_PER_DEG_LON_EQ
        y = (np.asarray(lat) - self._lat0) * M_PER_DEG_LAT
        return x, y

    @property
    def bbox(self) -> list[float]:
        return [float(self.node_lon.min()), float(self.node_lat.min()),
                float(self.node_lon.max()), float(self.node_lat.max())]

    @property
    def signal_count(self) -> int:
        return int(sum(self.node_is_signal))

    def nearest_node(self, lat: float, lon: float) -> tuple[int, float]:
        """Closest non-freeway node and the straight-line distance to it in metres."""
        x, y = self._project(lat, lon)
        dist, idx = self._tree.query([float(x), float(y)])
        return int(self._surface_ids[idx]), float(dist)

    def signal_key(self, node: int) -> int:
        return int(self.node_osm_id[node])

    def heuristic_to(self, dest: int) -> list[float]:
        """Admissible lower bound on travel time from every node to `dest`."""
        dx = self._px - self._px[dest]
        dy = self._py - self._py[dest]
        return (np.hypot(dx, dy) * 0.99 / self.max_speed_mps).tolist()

    def path_geometry(self, edges: list[int]) -> list[list[float]]:
        """Polyline for a list of edges as [lon, lat] pairs, rounded to ~10 cm."""
        coords: list[list[float]] = []
        for i, e in enumerate(edges):
            seg = self.geom_coords[self.geom_offsets[e]:self.geom_offsets[e + 1]]
            if i > 0:
                seg = seg[1:]
            coords.extend([round(float(lon), 6), round(float(lat), 6)] for lat, lon in seg)
        return coords
