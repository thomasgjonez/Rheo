"""Runs the routing engine against real intersection data: actual signalized
crossings along Market Street in San Francisco, geocoded from OpenStreetMap
(see data/market_street_signals.json and app/real_data.py).

Distances between intersections are computed from real coordinates
(haversine). Signal *timing* is a labeled assumption -- actual ATSPM/SPaT
timing plans for this corridor are not public data (see README.md); this
runs the same signal-aware algorithm against real geometry to prove the
pipeline works end to end on real-world input, not synthetic grid data.

Run: python3 demo_real.py
"""

from app.real_data import build_market_street_network, build_market_street_signals, load_intersections
from app.routing import RouteResult, find_route
from demo import BOLD, CYAN, DIM, GREEN, RED, RESET, render_departure_sweep, render_timeline


def render_corridor(intersections, result: RouteResult) -> None:
    stopped = {s.from_node for s in result.segments if s.stopped}
    n = len(intersections)
    for i, x in enumerate(intersections):
        node_id = f"m{i}"
        if i == 0:
            marker, tag = f"{BOLD}{CYAN}A{RESET}", ""
        elif i == n - 1:
            marker, tag = f"{BOLD}{CYAN}B{RESET}", ""
        elif node_id in stopped:
            marker, tag = f"{BOLD}{RED}X{RESET}", "  <- stopped for red"
        else:
            marker, tag = f"{GREEN}#{RESET}", ""
        print(f"  {marker}  {x['label']}{tag}")
        if i < n - 1:
            seg = result.segments[i]
            print(f"  {DIM}|{RESET}    {seg.travel_time_s:.0f}s drive"
                  + (f" + {seg.wait_time_s:.0f}s wait" if seg.stopped else ""))


def main() -> None:
    intersections = load_intersections()
    network = build_market_street_network()
    spat = build_market_street_signals(network)

    origin, destination = "m0", f"m{len(intersections) - 1}"
    base_time = 1_000_000.0

    print(f"{BOLD}=== Real corridor: Market Street, San Francisco ==={RESET}")
    print(f"  {len(intersections)} real signalized intersections, geocoded from OpenStreetMap.\n")

    for label, t in (("t=+0s", base_time), ("t=+20s", base_time + 20)):
        result = find_route(network, spat, origin, destination, departure_time_s=t)
        print(f"\n{BOLD}--- Depart {label} ---{RESET}  total: {result.total_time_s:.1f}s   "
              f"distance: {result.total_distance_m:.0f}m   stops: {result.stops}\n")
        render_corridor(intersections, result)
        render_timeline(result)

    render_departure_sweep(network, spat, origin, destination, base_time, span_s=90, step_s=5)


if __name__ == "__main__":
    main()
