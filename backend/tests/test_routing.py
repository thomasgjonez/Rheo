import random

import pytest

from rheo.routing import evaluate_path, find_route
from rheo.spat import SignalPlan, SimulatedSPaTProvider, StubSPaTProvider
from tests.grid import BLOCK_M, SPEED_MPS, ScriptedProvider, make_grid, node_id

DEPART = 1_800_000_000.0
BLOCK_S = BLOCK_M / SPEED_MPS


def test_without_signals_finds_shortest_path():
    g = make_grid(3, 3)
    route = find_route(g, StubSPaTProvider(), node_id(3, 3, 0, 0), node_id(3, 3, 2, 2), DEPART)
    assert len(route.edges) == 4
    assert route.total_time_s == pytest.approx(4 * BLOCK_S)
    assert route.stops == 0


def test_origin_equals_destination_is_empty_route():
    g = make_grid(3, 3)
    route = find_route(g, StubSPaTProvider(), 4, 4, DEPART)
    assert route.edges == [] and route.total_time_s == 0


def test_stub_reports_no_data_and_no_waits():
    g = make_grid(3, 3, signals={(1, 1)})
    route = find_route(g, StubSPaTProvider(), node_id(3, 3, 1, 0), node_id(3, 3, 1, 2), DEPART)
    assert [e.known for e in route.events] == [False]
    assert route.wait_s == 0 and route.stops == 0


def test_aware_route_detours_around_a_red_light():
    g = make_grid(3, 3, signals={(1, 1)})
    origin, dest = node_id(3, 3, 1, 0), node_id(3, 3, 1, 2)
    red = ScriptedProvider(wait=60.0)

    blind_pick = find_route(g, StubSPaTProvider(), origin, dest, DEPART)
    blind = evaluate_path(g, red, blind_pick.edges, DEPART)
    aware = find_route(g, red, origin, dest, DEPART)

    assert len(blind_pick.edges) == 2  # straight through the centre
    assert blind.total_time_s == pytest.approx(2 * BLOCK_S + 60.0)
    assert blind.stops == 1
    assert aware.total_time_s == pytest.approx(4 * BLOCK_S)  # around the top or bottom
    assert aware.stops == 0
    assert aware.edges != blind.edges


def test_aware_never_slower_than_blind_on_random_trips():
    rows = cols = 6
    g = make_grid(rows, cols, signals={(r, c) for r in range(rows) for c in range(cols)})
    sim, stub = SimulatedSPaTProvider(), StubSPaTProvider()
    rng = random.Random(3)
    for _ in range(25):
        o, d = rng.sample(range(rows * cols), 2)
        depart = DEPART + rng.uniform(0, 500)
        blind = evaluate_path(g, sim, find_route(g, stub, o, d, depart).edges, depart)
        aware = find_route(g, sim, o, d, depart)
        assert aware.total_time_s <= blind.total_time_s + 1e-6


def test_find_route_total_matches_independent_replay():
    g = make_grid(4, 4, signals={(1, 1), (2, 2)})
    sim = SimulatedSPaTProvider()
    route = find_route(g, sim, 0, 15, DEPART)
    replay = evaluate_path(g, sim, route.edges, DEPART)
    assert replay.total_time_s == pytest.approx(route.total_time_s)


def test_signal_plan_waits_until_next_green_and_wraps():
    plan = SignalPlan(cycle_s=100.0, green_windows=(((10.0, 40.0),), ((50.0, 90.0),)))
    assert plan.wait_s(0, 10.0) == 0.0
    assert plan.wait_s(0, 39.9) == 0.0
    assert plan.wait_s(0, 40.0) == pytest.approx(70.0)  # red until next cycle's 10s mark
    assert plan.wait_s(0, 0.0) == pytest.approx(10.0)
    assert plan.wait_s(1, 100.0 * 7 + 45.0) == pytest.approx(5.0)


def test_simulated_provider_is_deterministic_bounded_and_seed_dependent():
    a, b, c = SimulatedSPaTProvider(seed=1), SimulatedSPaTProvider(seed=1), SimulatedSPaTProvider(seed=2)
    waits_a = [a.wait_s(1000 + i, i % 2, DEPART + i * 7.3) for i in range(200)]
    waits_b = [b.wait_s(1000 + i, i % 2, DEPART + i * 7.3) for i in range(200)]
    waits_c = [c.wait_s(1000 + i, i % 2, DEPART + i * 7.3) for i in range(200)]
    assert waits_a == waits_b
    assert waits_a != waits_c
    assert all(0.0 <= w < 120.0 for w in waits_a)
    assert any(w == 0.0 for w in waits_a) and any(w > 0.0 for w in waits_a)


def test_simulated_signal_greens_alternate_between_approach_groups():
    sim = SimulatedSPaTProvider()
    plan = sim.plan(4242)
    for t in range(0, int(plan.cycle_s) * 2):
        both_green = plan.wait_s(0, DEPART + t) == 0 and plan.wait_s(1, DEPART + t) == 0
        assert not both_green
