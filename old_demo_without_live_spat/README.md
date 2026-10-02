# Rheo

Signal-aware routing prototype. Proves out the core mechanic: given signal timing data (SPaT), compute the
route that actually minimizes travel time or stops, accounting for which
lights you'll catch red vs. green *given when you arrive at them*. A
normal shortest-path router (Google/Apple Maps' base layer) treats every
intersection as a fixed cost; this treats it as a schedule.

## How it works

- `app/graph.py` — road network as nodes (intersections) and directed edges
  (road segments with distance/speed/type).
- `app/spat.py` — the SPaT integration seam. `SignalPlan` models a fixed
  green/red schedule per approach; `SPaTProvider` is the abstract interface
  routing.py depends on. `MockSPaTProvider` is the stand-in used here;
  swap in a class that calls a real feed (ATSPM export, vendor API,
  connected-vehicle SPaT broadcast) and nothing else needs to change.
  `plan_from_live_snapshot()` shows how to turn a single real-time
  "current phase + seconds to change" reading into the same model.
- `app/routing.py` — the actual algorithm: a time-dependent earliest-arrival
  search (a Dijkstra variant). The search state is `(node, incoming_edge)`
  rather than just `node`, because the wait at an intersection depends on
  which approach you came from (different approaches are green at
  different times). This is what makes it correctly turn/approach-aware
  rather than just intersection-aware.
- `app/network_data.py` — builds a demo 5x5 grid with a synchronized
  "green wave" along one axis, so the routing effects are visible.
- `app/main.py` — FastAPI wrapper exposing it as `POST /route`.

## Why this design choice: (node, incoming_edge) state, not just node

A plain Dijkstra over nodes assumes the cost to continue from a node is the
same no matter how you got there. That's false at a signalized
intersection — arriving via the eastbound approach vs. the northbound
approach can mean the difference between a green light and a 30-second
wait. Carrying the incoming edge in the search state costs little extra
code and is what real routing engines (OSRM, GraphHopper) already do to
handle turn restrictions/costs — this reuses the same trick for signal
phase.

## Run it

Directly, no server (fastest way to see it work):

```bash
python3 demo.py
```

As an API:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

Then:

```bash
curl -s -X POST http://127.0.0.1:8000/route \
  -H "Content-Type: application/json" \
  -d '{"origin": "n0_0", "destination": "n4_4", "departure_time": 1000000}'
```

`GET /network` returns the demo graph (for building a map visualization on
top of this).

### Request options

- `objective`: `"fastest"` (default) or `"fewest_stops"` — same search,
  different tie-break priority.
- `avoid_highways`: `true`/`false` — filters out edges tagged `highway`.
- `departure_time`: unix epoch seconds; omit to default to "now". Changing
  this is the whole point — the same origin/destination can have a
  different best route or ETA five seconds later, because you catch
  different lights.

## Running it on real data

`demo_real.py` runs the same algorithm against real intersections instead of
the synthetic grid: 8 actual signalized crossings along Market Street in San
Francisco, geocoded from OpenStreetMap via Nominatim (`data/market_street_signals.json`,
built by `app/real_data.py`). Distances between intersections are computed
from their real coordinates (haversine) -- these are genuine block lengths,
not made up.

```bash
python3 demo_real.py
```

**What's real here and what isn't**: intersection positions and the
distances between them are real (sourced from OpenStreetMap). Signal
*timing* (cycle length, offsets) is a labeled assumption, not real ATSPM/SPaT
data -- as covered above, that data isn't publicly available for this
corridor, which is itself the market-validation finding from earlier
(agencies and the incumbent vendors hold it, not the open web). So this
demonstrates the algorithm and data pipeline work end-to-end on real-world
geometry; it does not demonstrate real Market Street light timing, because
that data doesn't exist anywhere public to pull.

## What's simplified (and would need work for a real pilot)

- **Pretimed signal assumption.** `SignalPlan` models a fixed repeating
  cycle. Actuated/adaptive signals (which change timing based on live
  demand — increasingly the norm) don't have a knowable fixed future
  schedule; you'd need to re-query the feed frequently and/or build a
  short-horizon predictor rather than trust a static plan.
- **No congestion/travel-time variability.** Edge travel time is
  free-flow distance/speed. A real system would blend this with live or
  historical traffic speed data (which Google/Waze/Apple already have —
  this prototype only adds the signal-timing layer on top).
- **Approach-level phase, not full turn-movement phase.** Real signals can
  give northbound-through green while northbound-left is red
  (protected/permissive turns). This models one phase per incoming edge,
  not per turning movement. Extending the state to
  `(node, incoming_edge, outgoing_edge)` would capture that at the cost of
  a larger search space.
- **No confidence/uncertainty modeling.** Real SPaT predictions (especially
  projected forward in time, or from actuated signals) carry error bars
  that a production system should propagate into route choice (e.g. avoid
  routes with a "just barely" catch on a light where mistiming means a
  full extra cycle wait).
