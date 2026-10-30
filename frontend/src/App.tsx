import { useEffect, useMemo, useState } from "react";
import { MapView } from "./components/MapView";
import { Results } from "./components/Results";
import { SearchBox } from "./components/SearchBox";
import { ApiError, fetchRoute } from "./lib/api";
import { fmtClock, pinnedLabel } from "./lib/format";
import type { LightsView, Place, RouteResponse, SpatMode } from "./types";

type Field = "from" | "to";

const EXAMPLES: { name: string; from: Place; to: Place }[] = [
  {
    name: "Ferry Building to Golden Gate Park",
    from: { label: "Ferry Building", lat: 37.7955, lon: -122.3937 },
    to: { label: "Conservatory of Flowers", lat: 37.7726, lon: -122.4603 },
  },
  {
    name: "Golden Gate Bridge to the Mission",
    from: { label: "Golden Gate Bridge toll plaza", lat: 37.807, lon: -122.475 },
    to: { label: "24th St & Mission St", lat: 37.7522, lon: -122.4184 },
  },
  {
    name: "Dolores Park to Fisherman's Wharf",
    from: { label: "Mission Dolores Park", lat: 37.7596, lon: -122.4269 },
    to: { label: "Fisherman's Wharf", lat: 37.8087, lon: -122.4098 },
  },
];

const MAX_OFFSET_S = 120;

export default function App() {
  const [from, setFrom] = useState<Place | null>(null);
  const [to, setTo] = useState<Place | null>(null);
  const [fromText, setFromText] = useState("");
  const [toText, setToText] = useState("");
  const [active, setActive] = useState<Field>("from");
  const [offset, setOffset] = useState(0);
  const [lights, setLights] = useState<LightsView>("aware");
  const [result, setResult] = useState<RouteResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ?spat=live shows the real (currently empty) SPaT stub instead of the simulated timings.
  const spatMode = useMemo<SpatMode>(
    () => (new URLSearchParams(window.location.search).get("spat") === "live" ? "live" : "simulated"),
    [],
  );

  function setPlace(which: Field, place: Place | null) {
    if (which === "from") {
      setFrom(place);
      setFromText(place?.label ?? "");
      if (place && !to) setActive("to");
    } else {
      setTo(place);
      setToText(place?.label ?? "");
      if (place && !from) setActive("from");
    }
  }

  function pinned(lat: number, lon: number): Place {
    return { label: pinnedLabel(lat, lon), lat, lon };
  }

  function swap() {
    setFrom(to);
    setTo(from);
    setFromText(toText);
    setToText(fromText);
  }

  function reset() {
    setFrom(null);
    setTo(null);
    setFromText("");
    setToText("");
    setActive("from");
    setOffset(0);
  }

  function loadExample(i: number) {
    const ex = EXAMPLES[i];
    setFrom(ex.from);
    setTo(ex.to);
    setFromText(ex.from.label);
    setToText(ex.to.label);
    setOffset(0);
  }

  useEffect(() => {
    if (!from || !to) {
      setResult(null);
      setError(null);
      setLoading(false);
      return;
    }
    const ctrl = new AbortController();
    const handle = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const depart = Math.floor(Date.now() / 1000) + offset;
        const data = await fetchRoute(from, to, depart, spatMode, ctrl.signal);
        setResult(data);
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        setResult(null);
        setError(err instanceof ApiError ? err.message : "Couldn't reach the routing service. Is the backend running?");
      } finally {
        if (!ctrl.signal.aborted) setLoading(false);
      }
    }, 200);
    return () => {
      clearTimeout(handle);
      ctrl.abort();
    };
  }, [from, to, offset, spatMode]);

  const departClock = fmtClock(Math.floor(Date.now() / 1000) + offset);
  const ready = Boolean(from && to);

  return (
    <div className="app">
      <MapView
        from={from}
        to={to}
        result={result}
        lights={lights}
        onMapClick={(lat, lon) => setPlace(active, pinned(lat, lon))}
        onPinDrag={(which, lat, lon) => setPlace(which, pinned(lat, lon))}
      />

      <aside className="panel">
        {loading && <div className="progress" role="progressbar" aria-label="Finding routes" />}
        <div className="panel__scroll">
          <header className="brand">
            <svg className="brand__mark" viewBox="0 0 32 32" aria-hidden="true">
              <rect width="32" height="32" rx="8" fill="currentColor" />
              <path d="M8 22c4-9 8-9 12-4s4 0 4-6" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
            </svg>
            <div>
              <h1>Rheo</h1>
              <p>Routes that know when the lights change</p>
            </div>
          </header>

          <div className="notice" role="note">
            <span className="notice__tag">{spatMode === "live" ? "Live feed: not connected" : "Demo"}</span>
            {spatMode === "live"
              ? "No real signal data is connected yet, so no timing is applied."
              : "Signal timing here is simulated. Real SPaT data isn't connected yet."}
          </div>

          <div className="inputs">
            <SearchBox
              label="Start"
              marker="A"
              text={fromText}
              place={from}
              active={active === "from"}
              onText={setFromText}
              onPick={(p) => setPlace("from", p)}
              onClear={() => setPlace("from", null)}
              onFocus={() => setActive("from")}
            />
            <button type="button" className="swap" aria-label="Swap start and destination" onClick={swap} disabled={!from && !to}>
              &#8645;
            </button>
            <SearchBox
              label="Destination"
              marker="B"
              text={toText}
              place={to}
              active={active === "to"}
              onText={setToText}
              onPick={(p) => setPlace("to", p)}
              onClear={() => setPlace("to", null)}
              onFocus={() => setActive("to")}
            />
          </div>

          <div className="slider">
            <label htmlFor="offset">
              <span>Leave in</span>
              <span className="slider__value">
                {offset === 0 ? "now" : `${offset} s`} <small>({departClock})</small>
              </span>
            </label>
            <input
              id="offset"
              type="range"
              min={0}
              max={MAX_OFFSET_S}
              step={5}
              value={offset}
              onChange={(e) => setOffset(Number(e.target.value))}
            />
            <p className="slider__hint">Nudge it and watch the lights, and the best route, change.</p>
          </div>

          {!ready && (
            <div className="examples">
              <p>Click the map or search above, or try an example:</p>
              {EXAMPLES.map((ex, i) => (
                <button key={ex.name} type="button" className="chip" onClick={() => loadExample(i)}>
                  {ex.name}
                </button>
              ))}
            </div>
          )}

          {ready && (
            <button type="button" className="link-btn" onClick={reset}>
              Start over
            </button>
          )}

          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}

          {result && <Results result={result} lights={lights} onLights={setLights} />}

          {result?.spat.is_simulated && (
            <p className="fineprint">
              Each light runs a made-up 70&ndash;120 s cycle on the real clock. Lights aren&rsquo;t coordinated and
              there&rsquo;s no traffic. The savings show what perfect knowledge of the lights could do in this model,
              not a forecast for real roads.
            </p>
          )}

          <footer className="fineprint fineprint--footer">
            Roads &copy; OpenStreetMap contributors. Map tiles &copy; CARTO.
          </footer>
        </div>
      </aside>
    </div>
  );
}
