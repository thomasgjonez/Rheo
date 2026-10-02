"""Exercises the routing engine directly, no HTTP server needed -- with an
ASCII visualization of the grid + path, and a chart showing how ETA swings
depending purely on when you leave.

Run: python3 demo.py
"""

import sys

from app.graph import RoadNetwork
from app.network_data import add_local_bypass, build_demo_network, build_demo_signals
from app.routing import RouteResult, find_route
from app.spat import SPaTProvider

COLOR = sys.stdout.isatty()


def _c(code: str) -> str:
    return code if COLOR else ""


RESET = _c("\033[0m")
BOLD = _c("\033[1m")
DIM = _c("\033[2m")
GREEN = _c("\033[32m")
RED = _c("\033[31m")
YELLOW = _c("\033[33m")
CYAN = _c("\033[36m")


def render_grid(network: RoadNetwork, result: RouteResult, origin: str, destination: str, rows: int, cols: int) -> None:
    """Draws the intersection grid with the chosen path traced on it, and
    the intersection where a red light forced a stop marked in red."""
    edges_used = {(s.from_node, s.to_node) for s in result.segments}
    path_nodes = {origin} | {s.to_node for s in result.segments}
    stopped_nodes = {s.from_node for s in result.segments if s.stopped}

    print()
    for r in range(rows):
        line = []
        for c in range(cols):
            node_id = f"n{r}_{c}"
            if node_id == origin:
                marker = f"{BOLD}{CYAN}A{RESET}"
            elif node_id == destination:
                marker = f"{BOLD}{CYAN}B{RESET}"
            elif node_id in stopped_nodes:
                marker = f"{BOLD}{RED}X{RESET}"
            elif node_id in path_nodes:
                marker = f"{GREEN}#{RESET}"
            else:
                marker = f"{DIM}.{RESET}"
            line.append(marker)
            if c < cols - 1:
                right_id = f"n{r}_{c + 1}"
                if (node_id, right_id) in edges_used:
                    line.append(f"{GREEN}-->{RESET}")
                elif (right_id, node_id) in edges_used:
                    line.append(f"{GREEN}<--{RESET}")
                else:
                    line.append(f"{DIM}---{RESET}")
        print("".join(line))

        if r < rows - 1:
            vline = []
            for c in range(cols):
                node_id = f"n{r}_{c}"
                down_id = f"n{r + 1}_{c}"
                if (node_id, down_id) in edges_used:
                    ch = f"{GREEN}v{RESET}"
                elif (down_id, node_id) in edges_used:
                    ch = f"{GREEN}^{RESET}"
                else:
                    ch = f"{DIM}|{RESET}"
                vline.append(ch)
                if c < cols - 1:
                    vline.append("   ")
            print("".join(vline))

    print(f"\n  {CYAN}A{RESET}=origin  {CYAN}B{RESET}=destination  "
          f"{GREEN}#{RESET}=path (clear)  {RED}X{RESET}=stopped for red  {DIM}.{RESET}=unused intersection")

    # Shortcuts (e.g. a local-road bypass) skip over a grid cell and can't be
    # drawn as a straight connector line above -- call them out explicitly.
    for seg in result.segments:
        fr, fc = (int(x) for x in seg.from_node[1:].split("_"))
        tr, tc = (int(x) for x in seg.to_node[1:].split("_"))
        if abs(fr - tr) + abs(fc - tc) > 1:
            print(f"  {YELLOW}(shortcut){RESET} {seg.from_node} ==> {seg.to_node} "
                  f"(off-grid side street, {seg.travel_time_s:.0f}s, no signal)")


def render_timeline(result: RouteResult) -> None:
    """Horizontal bar per road segment: green = driving, red = waiting at a light."""
    print(f"\n  {BOLD}Segment timeline{RESET} (each block ~2s)")
    for seg in result.segments:
        drive_blocks = max(1, round(seg.travel_time_s / 2))
        wait_blocks = round(seg.wait_time_s / 2)
        bar = f"{GREEN}{'#' * drive_blocks}{RESET}{RED}{'#' * wait_blocks}{RESET}"
        note = f"  wait {seg.wait_time_s:.0f}s at red" if seg.stopped else ""
        print(f"  {seg.from_node:>6} -> {seg.to_node:<6} {bar}{note}")


def show(result: RouteResult, network: RoadNetwork, origin: str, destination: str, rows: int, cols: int, label: str) -> None:
    print(f"\n{BOLD}=== {label} ==={RESET}")
    if not result.found:
        print("no route found")
        return
    print(f"total time: {BOLD}{result.total_time_s:.1f}s{RESET}   "
          f"distance: {result.total_distance_m:.0f}m   stops: {result.stops}")
    render_grid(network, result, origin, destination, rows, cols)
    render_timeline(result)


def render_departure_sweep(
    network: RoadNetwork,
    spat: SPaTProvider,
    origin: str,
    destination: str,
    base_time: float,
    span_s: int = 90,
    step_s: int = 3,
) -> None:
    """The real point of the whole idea: the SAME trip has a different ETA
    purely depending on when you leave, because you catch different points
    in the signal cycle. This sweeps departure time and charts it."""
    offsets = list(range(0, span_s, step_s))
    times = []
    for off in offsets:
        r = find_route(network, spat, origin, destination, departure_time_s=base_time + off)
        times.append(r.total_time_s if r.found else None)

    valid = [t for t in times if t is not None]
    lo, hi = min(valid), max(valid)
    width = 40

    print(f"\n{BOLD}=== Same trip, different departure times ==={RESET}")
    print(f"  ETA for {origin} -> {destination}, leaving N seconds from now:\n")
    for off, t in zip(offsets, times):
        if t is None:
            continue
        frac = (t - lo) / (hi - lo) if hi > lo else 0.0
        bar_len = max(1, round(frac * width))
        color = RED if t == hi else (GREEN if t == lo else YELLOW)
        print(f"  +{off:>3}s   {t:5.1f}s  {color}{'#' * bar_len}{RESET}")

    print(f"\n  Same origin, same destination, same route options -- but a "
          f"{BOLD}{hi - lo:.0f}s{RESET} swing in ETA depending only on which "
          f"second you leave. That's the timing signal a normal (signal-blind)\n"
          f"  router can't see, and it's the whole value proposition: predicting "
          f"it turns a fixed cost into something you can route around.")


def render_fork_scenario(rows: int, cols: int, origin: str, destination: str, base_time: float) -> None:
    """Adds a real fork in the road: a longer, signal-free side-street
    shortcut around the one intersection that has a bad light. Shows the
    router actually switching which path it takes -- trading distance for
    a green light -- depending on when you'd hit that intersection."""
    print(f"\n{BOLD}=== Does it take the shortcut? A real fork in the road ==={RESET}")

    network = build_demo_network(rows=rows, cols=cols)
    spat = build_demo_signals(network)

    direct_via = ("n0_4", "n1_4", "n2_4")  # arterial, through the light-controlled n1_4 approach
    bypass_distance_m = 450.0  # vs. 300m for the two direct arterial blocks
    add_local_bypass(network, direct_via[0], direct_via[2], distance_m=bypass_distance_m, speed_mps=12.5)

    print(f"  Two ways from {direct_via[0]} to {direct_via[2]}: the arterial through the signalized\n"
          f"  approach at {direct_via[1]} (300m), or a {bypass_distance_m:.0f}m side-street bypass with no signal.\n"
          f"  Same origin/destination trip ({origin} -> {destination}) either way -- only the middle differs.")

    for label, t in (("bad light timing", base_time), ("good light timing", base_time + 15)):
        result = find_route(network, spat, origin, destination, departure_time_s=t)
        took_bypass = any(s.edge_id == f"{direct_via[0]}=>{direct_via[2]}" for s in result.segments)
        choice = f"{YELLOW}the BYPASS{RESET} (gave up distance to dodge the red)" if took_bypass \
            else f"{GREEN}the DIRECT arterial{RESET} (the light wasn't worth avoiding)"
        print(f"\n  {BOLD}Departing with {label}{RESET} (t=+{t - base_time:.0f}s): "
              f"total {result.total_time_s:.1f}s -- router chose {choice}")
        render_grid(network, result, origin, destination, rows, cols)


def main() -> None:
    rows, cols = 5, 5
    network = build_demo_network(rows=rows, cols=cols)
    spat = build_demo_signals(network)

    origin, destination = "n0_0", "n4_4"
    base_time = 1_000_000.0  # arbitrary reference epoch, seconds

    r1 = find_route(network, spat, origin, destination, departure_time_s=base_time)
    show(r1, network, origin, destination, rows, cols, f"Depart t={base_time:.0f}s, objective=fastest")

    r2 = find_route(network, spat, origin, destination, departure_time_s=base_time + 15)
    show(r2, network, origin, destination, rows, cols, f"Depart t={base_time + 15:.0f}s, objective=fastest")

    r3 = find_route(network, spat, origin, destination, departure_time_s=base_time, objective="fewest_stops")
    show(r3, network, origin, destination, rows, cols, f"Depart t={base_time:.0f}s, objective=fewest_stops")

    render_departure_sweep(network, spat, origin, destination, base_time)

    render_fork_scenario(rows, cols, origin, destination, base_time)


if __name__ == "__main__":
    main()
