"""Address search via the public Photon geocoder (OpenStreetMap data).

Proxied through the backend so the browser never talks to a third party directly, the geocoder
can be swapped later without touching the frontend, and responses can be cached.
Photon's public instance is fair-use only; point PHOTON_URL at your own instance for real traffic.
"""

from __future__ import annotations

import os
from functools import lru_cache

import httpx

PHOTON_URL = os.environ.get("PHOTON_URL", "https://photon.komoot.io/api/")
USER_AGENT = "Rheo-demo/0.1 (+https://github.com/thomasgjonez/Rheo)"


class GeocodeError(RuntimeError):
    pass


def _label(props: dict) -> str:
    street = " ".join(p for p in (props.get("housenumber"), props.get("street")) if p)
    parts = [props.get("name"), street, props.get("city") or props.get("county")]
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return ", ".join(seen) or "Unnamed place"


@lru_cache(maxsize=512)
def _cached(query: str, bbox: tuple[float, float, float, float], limit: int) -> tuple[dict, ...]:
    center_lon, center_lat = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    params = {
        "q": query,
        "limit": limit * 2,
        "lang": "en",
        "lat": f"{center_lat:.5f}",
        "lon": f"{center_lon:.5f}",
        "bbox": ",".join(f"{v:.5f}" for v in bbox),
    }
    try:
        resp = httpx.get(PHOTON_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=6.0)
        resp.raise_for_status()
        features = resp.json().get("features", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise GeocodeError(str(exc)) from exc

    results = []
    seen_labels: set[str] = set()
    for feature in features:
        lon, lat = feature["geometry"]["coordinates"]
        if not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
            continue
        label = _label(feature.get("properties", {}))
        if label in seen_labels:
            continue
        seen_labels.add(label)
        results.append({"label": label, "lat": lat, "lon": lon})
        if len(results) >= limit:
            break
    return tuple(results)


def search(query: str, bbox: tuple[float, float, float, float], limit: int = 6) -> list[dict]:
    query = query.strip()
    if len(query) < 3:
        return []
    return list(_cached(query.lower(), tuple(round(v, 5) for v in bbox), limit))
