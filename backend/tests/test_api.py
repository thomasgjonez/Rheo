import pytest
from fastapi.testclient import TestClient

from rheo.api import create_app
from tests.grid import LAT0, LON0, STEP_LAT, STEP_LON, make_grid

DEPART = 1_800_000_000.0


@pytest.fixture(scope="module")
def client():
    rows = cols = 5
    graph = make_grid(rows, cols, signals={(r, c) for r in range(rows) for c in range(cols)})
    with TestClient(create_app(graph=graph)) as c:
        yield c


def point(r, c):
    return {"lat": LAT0 + r * STEP_LAT, "lon": LON0 + c * STEP_LON}


def test_health_and_meta(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    meta = client.get("/api/meta").json()
    assert meta["signals"] == 25
    assert {m["id"]: m["connected"] for m in meta["spat_modes"]} == {"simulated": True, "live": False}


def test_route_simulated_returns_both_routes_and_comparison(client):
    body = {"origin": point(0, 0), "destination": point(4, 4), "depart_epoch": DEPART}
    data = client.post("/api/route", json=body).json()
    assert data["spat"]["is_simulated"] is True
    assert data["aware"]["total_time_s"] <= data["blind"]["total_time_s"]
    assert data["comparison"]["time_saved_s"] == pytest.approx(
        data["blind"]["total_time_s"] - data["aware"]["total_time_s"], abs=0.11
    )
    assert data["aware"]["geometry"][0] == pytest.approx([LON0, LAT0], abs=1e-5)
    assert data["aware"]["signals_with_data"] == data["aware"]["signals_on_route"] > 0


def test_route_live_mode_uses_empty_stub(client):
    body = {"origin": point(0, 0), "destination": point(4, 4), "depart_epoch": DEPART, "spat_mode": "live"}
    data = client.post("/api/route", json=body).json()
    assert data["spat"]["connected"] is False
    assert data["comparison"]["same_route"] is True
    assert data["aware"]["signals_with_data"] == 0
    assert data["aware"]["wait_s"] == 0 and data["aware"]["stops"] == 0


def test_route_rejects_points_outside_coverage(client):
    far = {"lat": 40.7, "lon": -74.0}
    resp = client.post("/api/route", json={"origin": far, "destination": point(1, 1)})
    assert resp.status_code == 422 and "demo area" in resp.json()["detail"]


def test_route_rejects_identical_points(client):
    resp = client.post("/api/route", json={"origin": point(2, 2), "destination": point(2, 2)})
    assert resp.status_code == 422


def test_route_validates_coordinates(client):
    resp = client.post("/api/route", json={"origin": {"lat": 999, "lon": 0}, "destination": point(1, 1)})
    assert resp.status_code == 422
