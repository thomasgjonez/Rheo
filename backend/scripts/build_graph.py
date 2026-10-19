#!/usr/bin/env python3
"""Build Rheo's drivable road graph from an OpenStreetMap .pbf extract.

Usage (from backend/):
    python scripts/build_graph.py ../data/raw/SanFrancisco.osm.pbf ../data/sf_graph.npz

The graph keeps only intersections/endpoints/signals as nodes, one directed
edge per drivable segment (with its polyline for drawing), and flags nodes that
OSM tags as highway=traffic_signals. Only the largest strongly connected
component is kept so every node can reach every other.

Map data (c) OpenStreetMap contributors, ODbL.
"""

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import osmium
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

HIGHWAY_CLASSES = [
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street",
]
CLASS_INDEX = {h: i for i, h in enumerate(HIGHWAY_CLASSES)}
FREEWAY_CLASSES = {CLASS_INDEX["motorway"], CLASS_INDEX["motorway_link"]}

DEFAULT_MPH = {
    "motorway": 50, "motorway_link": 30, "trunk": 35, "trunk_link": 25,
    "primary": 30, "primary_link": 25, "secondary": 25, "secondary_link": 25,
    "tertiary": 25, "tertiary_link": 25, "unclassified": 25, "residential": 25,
    "living_street": 15,
}
IMPLIED_ONEWAY = {"motorway", "motorway_link"}
MPH_TO_MPS = 0.44704
# Posted limits overstate city free-flow speeds, and OSM stop signs are too inconsistently tagged to model
# directly, so effective speed is the posted limit times a factor by road class. Local streets get a much
# lower factor: in a city like SF they have a stop sign nearly every block, and without this the router
# would treat them as free-flowing shortcuts.
SPEED_FACTOR_BY_CLASS = {
    "motorway": 0.90, "motorway_link": 0.80, "trunk": 0.85, "trunk_link": 0.75,
    "primary": 0.85, "primary_link": 0.75, "secondary": 0.85, "secondary_link": 0.75,
    "tertiary": 0.75, "tertiary_link": 0.70, "unclassified": 0.55, "residential": 0.50,
    "living_street": 0.50,
}


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def parse_speed_mph(value, default):
    if not value:
        return default
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kmh|kph)?\s*$", value.lower())
    if not m:
        return default
    number, unit = float(m.group(1)), m.group(2)
    return number if unit == "mph" else number * 0.621371


def is_drivable(tags):
    highway = tags.get("highway")
    if highway not in CLASS_INDEX or tags.get("area") == "yes":
        return False
    if tags.get("motor_vehicle") in ("yes", "designated", "permissive"):
        return True
    return tags.get("access") not in ("no", "private") and tags.get("motor_vehicle") not in ("no", "private")


def oneway_direction(tags, highway):
    value = tags.get("oneway")
    if value in ("yes", "true", "1"):
        return 1
    if value in ("-1", "reverse"):
        return -1
    if value in ("no", "false", "0"):
        return 0
    if tags.get("junction") == "roundabout" or highway in IMPLIED_ONEWAY:
        return 1
    return 0


class Collector(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.signals = set()
        self.ways = []

    def node(self, n):
        if n.tags.get("highway") == "traffic_signals":
            self.signals.add(n.id)

    def way(self, w):
        tags = w.tags
        if not is_drivable(tags):
            return
        points = []
        try:
            for nd in w.nodes:
                if not nd.location.valid():
                    return
                points.append((nd.ref, nd.location.lat, nd.location.lon))
        except osmium.InvalidLocationError:
            return
        if len(points) < 2:
            return
        highway = tags.get("highway")
        self.ways.append({
            "points": points,
            "highway": highway,
            "oneway": oneway_direction(tags, highway),
            "maxspeed": tags.get("maxspeed"),
            "name": tags.get("name") or "",
        })


def build(pbf_path: Path, out_path: Path) -> None:
    print(f"Reading {pbf_path} ...")
    collector = Collector()
    collector.apply_file(str(pbf_path), locations=True)
    ways, signals = collector.ways, collector.signals
    print(f"  {len(ways):,} drivable ways, {len(signals):,} signal nodes in extract")

    use_count = defaultdict(int)
    for way in ways:
        for ref, _, _ in way["points"]:
            use_count[ref] += 1

    node_index = {}
    node_osm_id, node_lat, node_lon, node_is_signal = [], [], [], []

    def get_node(ref, lat, lon):
        idx = node_index.get(ref)
        if idx is None:
            idx = len(node_osm_id)
            node_index[ref] = idx
            node_osm_id.append(ref)
            node_lat.append(lat)
            node_lon.append(lon)
            node_is_signal.append(ref in signals)
        return idx

    names, name_index = [""], {"": 0}
    e_from, e_to, e_len, e_speed, e_class, e_bearing, e_name = [], [], [], [], [], [], []
    e_geom = []  # list of (lat, lon) tuples per edge

    def add_edge(u, v, pts, length, speed, cls, name_idx):
        e_from.append(u)
        e_to.append(v)
        e_len.append(length)
        e_speed.append(speed)
        e_class.append(cls)
        e_name.append(name_idx)
        e_geom.append(pts)
        # approach heading: direction of travel over the last few metres of the edge
        end_lat, end_lon = pts[-1]
        back = pts[-2]
        for p in reversed(pts[:-1]):
            back = p
            if haversine_m(p[0], p[1], end_lat, end_lon) >= 3.0:
                break
        e_bearing.append(bearing_deg(back[0], back[1], end_lat, end_lon))

    for way in ways:
        pts = way["points"]
        cls = CLASS_INDEX[way["highway"]]
        mph = parse_speed_mph(way["maxspeed"], DEFAULT_MPH[way["highway"]])
        speed = mph * MPH_TO_MPS * SPEED_FACTOR_BY_CLASS[way["highway"]]
        name = way["name"]
        if name not in name_index:
            name_index[name] = len(names)
            names.append(name)
        name_idx = name_index[name]

        cut_positions = [0]
        for i in range(1, len(pts) - 1):
            ref = pts[i][0]
            if use_count[ref] >= 2 or ref in signals:
                cut_positions.append(i)
        cut_positions.append(len(pts) - 1)

        for a, b in zip(cut_positions, cut_positions[1:]):
            seg = pts[a:b + 1]
            coords = [(lat, lon) for _, lat, lon in seg]
            length = sum(haversine_m(*coords[i], *coords[i + 1]) for i in range(len(coords) - 1))
            if length <= 0.0:
                continue
            u = get_node(seg[0][0], seg[0][1], seg[0][2])
            v = get_node(seg[-1][0], seg[-1][1], seg[-1][2])
            if u == v:
                continue
            direction = way["oneway"]
            if direction >= 0:
                add_edge(u, v, coords, length, speed, cls, name_idx)
            if direction <= 0:
                add_edge(v, u, coords[::-1], length, speed, cls, name_idx)

    n, m = len(node_osm_id), len(e_from)
    print(f"  raw graph: {n:,} nodes, {m:,} edges")

    ef, et = np.array(e_from, dtype=np.int64), np.array(e_to, dtype=np.int64)
    adjacency = coo_matrix((np.ones(m, dtype=np.int8), (ef, et)), shape=(n, n))
    _, labels = connected_components(adjacency, directed=True, connection="strong")
    biggest = np.bincount(labels).argmax()
    keep_node = labels == biggest
    keep_edge = keep_node[ef] & keep_node[et]
    remap = -np.ones(n, dtype=np.int64)
    remap[keep_node] = np.arange(int(keep_node.sum()))

    nodes_kept = np.nonzero(keep_node)[0]
    edges_kept = np.nonzero(keep_edge)[0]
    print(f"  largest strongly connected component: {len(nodes_kept):,} nodes, {len(edges_kept):,} edges")

    out_from = remap[ef[edges_kept]].astype(np.int32)
    out_to = remap[et[edges_kept]].astype(np.int32)
    class_arr = np.array(e_class, dtype=np.uint8)[edges_kept]

    geom_offsets = np.zeros(len(edges_kept) + 1, dtype=np.int64)
    flat = []
    for k, e in enumerate(edges_kept):
        flat.extend(e_geom[e])
        geom_offsets[k + 1] = len(flat)
    geom_coords = np.array(flat, dtype=np.float64)

    # Human-readable label for each signalized intersection, e.g. "Market Street & 5th Street".
    incident = defaultdict(set)
    for k, e in enumerate(edges_kept):
        nm = names[e_name[e]]
        if nm:
            for node in (int(out_from[k]), int(out_to[k])):
                incident[node].add((int(class_arr[k]), nm))
    node_is_signal_kept = np.array(node_is_signal, dtype=bool)[nodes_kept]
    labels_out = []
    for new_idx in range(len(nodes_kept)):
        if node_is_signal_kept[new_idx]:
            distinct = []
            for _, nm in sorted(incident.get(new_idx, set())):
                if nm not in distinct:
                    distinct.append(nm)
            labels_out.append(" & ".join(distinct[:2]) if distinct else "Signalized intersection")
        else:
            labels_out.append("")

    lat_arr = np.array(node_lat, dtype=np.float64)[nodes_kept]
    lon_arr = np.array(node_lon, dtype=np.float64)[nodes_kept]
    meta = {
        "source": pbf_path.name,
        "attribution": "(c) OpenStreetMap contributors (ODbL)",
        "speed_factor_by_class": SPEED_FACTOR_BY_CLASS,
        "bbox": [float(lon_arr.min()), float(lat_arr.min()), float(lon_arr.max()), float(lat_arr.max())],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        node_osm_id=np.array(node_osm_id, dtype=np.int64)[nodes_kept],
        node_lat=lat_arr,
        node_lon=lon_arr,
        node_is_signal=node_is_signal_kept,
        node_label=np.array(labels_out, dtype="<U96"),
        edge_from=out_from,
        edge_to=out_to,
        edge_length_m=np.array(e_len, dtype=np.float32)[edges_kept],
        edge_speed_mps=np.array(e_speed, dtype=np.float32)[edges_kept],
        edge_class=class_arr,
        edge_end_bearing=np.array(e_bearing, dtype=np.float32)[edges_kept],
        geom_offsets=geom_offsets,
        geom_coords=geom_coords,
        meta=np.array(json.dumps(meta)),
    )
    sig_count = int(node_is_signal_kept.sum())
    print(f"Wrote {out_path} ({out_path.stat().st_size / 1e6:.1f} MB): "
          f"{len(nodes_kept):,} nodes, {len(edges_kept):,} edges, {sig_count:,} signals")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pbf", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    if not args.pbf.exists():
        sys.exit(f"missing input: {args.pbf}")
    build(args.pbf, args.out)
