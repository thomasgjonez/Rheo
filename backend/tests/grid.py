"""Tiny synthetic road graphs for tests."""

from __future__ import annotations

import numpy as np

from rheo.graph import RoadGraph
from rheo.spat import SPaTProvider

LAT0, LON0 = 37.77, -122.42
STEP_LAT, STEP_LON = 0.0009, 0.00113  # ~100 m
BLOCK_M = 100.0
SPEED_MPS = 10.0  # 10 s per block


def node_id(rows: int, cols: int, r: int, c: int) -> int:
    return r * cols + c


def make_grid(rows: int, cols: int, signals: set[tuple[int, int]] | None = None) -> RoadGraph:
    signals = signals or set()
    lat = np.array([LAT0 + r * STEP_LAT for r in range(rows) for _ in range(cols)])
    lon = np.array([LON0 + c * STEP_LON for _ in range(rows) for c in range(cols)])
    is_signal = np.array([(r, c) in signals for r in range(rows) for c in range(cols)])

    e_from, e_to, bearings, geom = [], [], [], []
    for r in range(rows):
        for c in range(cols):
            for dr, dc, bearing in ((0, 1, 90.0), (0, -1, 270.0), (1, 0, 0.0), (-1, 0, 180.0)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < rows and 0 <= cc < cols:
                    u, v = node_id(rows, cols, r, c), node_id(rows, cols, rr, cc)
                    e_from.append(u)
                    e_to.append(v)
                    bearings.append(bearing)
                    geom.extend([(lat[u], lon[u]), (lat[v], lon[v])])
    m = len(e_from)
    return RoadGraph({
        "node_osm_id": np.arange(1000, 1000 + rows * cols),
        "node_lat": lat,
        "node_lon": lon,
        "node_label": np.array([f"Node {i}" if s else "" for i, s in enumerate(is_signal)]),
        "node_is_signal": is_signal,
        "edge_from": np.array(e_from),
        "edge_to": np.array(e_to),
        "edge_length_m": np.full(m, BLOCK_M),
        "edge_speed_mps": np.full(m, SPEED_MPS),
        "edge_class": np.full(m, 11, dtype=np.uint8),  # residential, so nodes are snappable
        "edge_end_bearing": np.array(bearings),
        "geom_offsets": np.arange(0, 2 * m + 1, 2),
        "geom_coords": np.array(geom),
    })


class ScriptedProvider(SPaTProvider):
    """Constant wait for every signal, regardless of time or approach."""

    name = "scripted"
    label = "Scripted test provider"
    is_simulated = True

    def __init__(self, wait: float):
        self.wait = wait

    def wait_s(self, signal_id, phase_group, t_epoch):
        return self.wait
