# Rheo

Routes that know when the lights change. Rheo folds traffic-signal timing (SPaT: Signal Phase and Timing)
into route calculation, so it can pick the path that hits the fewest red lights instead of just the shortest one.

This repo is a working demo: enter two places in San Francisco and Rheo shows the fastest route a
signal-blind router would pick next to the route it picks when it knows the lights.

## What is real and what is simulated

| Piece | Status |
| --- | --- |
| Road network and signal **locations** (3,030 signalized intersections) | Real, from OpenStreetMap |
| Routing algorithm (time-dependent A* over directed edges) | Real |
| Signal **timing** | **Simulated.** No real SPaT feed is connected. |

Real signal timing is not publicly available for most intersections; it sits with city agencies and signal
vendors. Until it is connected, the demo uses made-up timing: every signal gets a fixed 70-120 s cycle and
offset (derived from its OSM id) and runs on the real clock. Lights are independent (no corridor coordination)
and there is no traffic, so the savings show what perfect knowledge of the lights could do in this model.
They are not a forecast for real roads. The UI says so wherever savings are shown.

`?spat=live` in the URL switches to the real provider, which is currently a stub that returns no data.

## Run it

Needs Python 3.11+ and Node 20+.

```bash
make setup     # venv, Python deps, npm install
make serve     # downloads the SF extract, builds the graph + frontend, serves http://localhost:8000
```

For development with hot reload, run `make api` and `make web` in two terminals and open http://localhost:5173.
`make test` runs the backend tests and a production frontend build.

## How it works

```
backend/
  scripts/build_graph.py   OSM .pbf -> compact drivable graph (data/sf_graph.npz), signals flagged
  rheo/graph.py            in-memory graph, nearest-road snapping
  rheo/routing.py          find_route (A*) and evaluate_path (replay a fixed path against a provider)
  rheo/spat/               SPaTProvider interface, StubSPaTProvider, SimulatedSPaTProvider
  rheo/api.py              FastAPI: /api/route, /api/geocode, /api/meta, /api/health
frontend/                  React + Vite + MapLibre
old_demo_without_live_spat/  the earlier terminal prototype, kept for reference
```

**The comparison.** For each request Rheo first finds the route a signal-blind router would choose, then
replays that exact path against the signals to see what it really costs. It then searches again with the
signals known. The signal-aware route is never slower than the blind one under the same timing.

**Routing.** The search state is the edge just traveled, not just the node, because the wait at a signal
depends on which approach you arrive by. Waits are non-negative and arriving earlier never makes you leave
later, so A* with a straight-line, top-speed lower bound stays correct. U-turns are disallowed.

**Plugging in real SPaT.** Implement `SPaTProvider.wait_s(signal_id, phase_group, t_epoch)` and return the
seconds a vehicle arriving at `t_epoch` waits for green, or `None` for no data. `signal_id` is the OSM node
id; `phase_group` is 0 (roughly north/south approach) or 1 (roughly east/west). Candidate sources: an agency
SPaT/ATSPM feed, or timing inferred from floating car data (see arXiv:2507.14190).

## Known simplifications

- Two approach groups per signal, by heading. Real signals have protected/permissive turns and more phases.
- Pretimed plans only. Actuated signals need a plan refreshed from live data.
- Speeds are posted limits times a factor per road class. Local streets are heavily discounted to stand in for
  stop signs, which OSM tags too inconsistently to model directly. No congestion.
- Start and end points snap to the nearest intersection, so a point mid-block is routed from the corner.
- Departure time is the request time plus the slider offset, so results change with the clock.

## Data and services

Map data (c) OpenStreetMap contributors, ODbL. The extract comes from BBBike. Basemap tiles are CARTO
Positron (free for non-commercial use; use your own tile provider for anything public). Address search uses
the public Photon geocoder, which is fair-use only; set `PHOTON_URL` to run your own for real traffic.
