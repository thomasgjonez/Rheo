import { fmtClock, fmtDuration, fmtMiles } from "../lib/format";
import type { LightsView, RouteResponse, RouteSummary } from "../types";

interface Props {
  result: RouteResponse;
  lights: LightsView;
  onLights: (v: LightsView) => void;
}

function headline(r: RouteResponse): { title: string; sub: string; tone: "good" | "neutral" } {
  const c = r.comparison;
  const pct = r.blind.total_time_s > 0 ? Math.round((c.time_saved_s / r.blind.total_time_s) * 100) : 0;
  const stopsText =
    c.stops_avoided > 0 ? `${c.stops_avoided} fewer red light${c.stops_avoided === 1 ? "" : "s"}` : null;

  if (!r.spat.connected) {
    return {
      title: "No live signal data yet",
      sub: "The SPaT feed isn't connected, so this is an ordinary fastest route with no signal timing applied.",
      tone: "neutral",
    };
  }
  if (c.time_saved_s >= 10) {
    return {
      title: `Rheo saves ${fmtDuration(c.time_saved_s)}`,
      sub: [`${pct}% faster`, stopsText, r.spat.is_simulated ? "simulated lights" : null].filter(Boolean).join(" · "),
      tone: "good",
    };
  }
  if (c.same_route) {
    return {
      title: "Same route either way",
      sub:
        r.blind.signals_on_route === 0
          ? "There are no traffic lights on this trip, so signal timing doesn't matter."
          : "No better path at this departure time. Try leaving a few seconds earlier or later.",
      tone: "neutral",
    };
  }
  return {
    title: "About the same time",
    sub: stopsText ? `${stopsText}, but no real time savings on this trip.` : "No meaningful difference on this trip.",
    tone: "neutral",
  };
}

function Row({ label, blind, aware, single }: { label: string; blind: string; aware: string; single: boolean }) {
  return (
    <tr>
      <th scope="row">{label}</th>
      <td>{blind}</td>
      {!single && <td className="is-aware">{aware}</td>}
    </tr>
  );
}

function rows(b: RouteSummary, a: RouteSummary, single: boolean) {
  return (
    <>
      <Row label="Arrive" blind={fmtClock(b.arrival_epoch)} aware={fmtClock(a.arrival_epoch)} single={single} />
      <Row label="Total time" blind={fmtDuration(b.total_time_s)} aware={fmtDuration(a.total_time_s)} single={single} />
      <Row label="Driving" blind={fmtDuration(b.drive_time_s)} aware={fmtDuration(a.drive_time_s)} single={single} />
      <Row label="Waiting at lights" blind={fmtDuration(b.wait_s)} aware={fmtDuration(a.wait_s)} single={single} />
      <Row label="Red lights hit" blind={String(b.stops)} aware={String(a.stops)} single={single} />
      <Row label="Lights passed" blind={String(b.signals_on_route)} aware={String(a.signals_on_route)} single={single} />
      <Row label="Distance" blind={fmtMiles(b.distance_m)} aware={fmtMiles(a.distance_m)} single={single} />
    </>
  );
}

export function Results({ result, lights, onLights }: Props) {
  const h = headline(result);
  const single = !result.spat.connected;
  const { blind, aware } = result;

  return (
    <section className="results" aria-live="polite">
      <div className={`headline headline--${h.tone}`}>
        <div className="headline__title">{h.title}</div>
        <div className="headline__sub">{h.sub}</div>
      </div>

      <table className="compare">
        <thead>
          <tr>
            <th />
            <th scope="col">
              <span className={`swatch ${single ? "swatch--aware" : "swatch--blind"}`} aria-hidden="true" />
              {single ? "Fastest route" : "Signal-blind"}
            </th>
            {!single && (
              <th scope="col" className="is-aware">
                <span className="swatch swatch--aware" aria-hidden="true" />
                Rheo
              </th>
            )}
          </tr>
        </thead>
        <tbody>{rows(blind, aware, single)}</tbody>
      </table>

      {single && (
        <p className="coverage">
          {blind.signals_with_data} of {blind.signals_on_route} signals on this route have timing data.
        </p>
      )}

      <div className="lights-toggle" role="group" aria-label="Show traffic lights on map">
        <span className="lights-toggle__label">Lights on map</span>
        {(single ? (["aware", "off"] as const) : (["aware", "blind", "off"] as const)).map((v) => (
          <button key={v} type="button" aria-pressed={lights === v} onClick={() => onLights(v)}>
            {v === "aware" ? (single ? "On" : "Rheo route") : v === "blind" ? "Signal-blind" : "Off"}
          </button>
        ))}
      </div>
    </section>
  );
}
