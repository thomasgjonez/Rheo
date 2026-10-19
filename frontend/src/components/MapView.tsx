import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import {
  AttributionControl,
  LngLatBounds,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  Popup,
  setWorkerUrl,
  type GeoJSONSource,
} from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { fmtClock } from "../lib/format";
import type { LightsView, Place, RouteResponse, RouteSummary } from "../types";

// MapLibre locates its worker relative to its own file, which breaks under Vite's bundling.
setWorkerUrl(workerUrl);

const MAP_STYLE =
  import.meta.env.VITE_MAP_STYLE_URL ?? "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";
const SF_CENTER: [number, number] = [-122.4375, 37.7595];

interface FeatureCollection {
  type: "FeatureCollection";
  features: unknown[];
}

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

function lineData(route: RouteSummary | null): FeatureCollection {
  if (!route || route.geometry.length < 2) return EMPTY;
  return {
    type: "FeatureCollection",
    features: [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: route.geometry } }],
  };
}

function signalData(route: RouteSummary | null): FeatureCollection {
  if (!route) return EMPTY;
  return {
    type: "FeatureCollection",
    features: route.signals.map((s) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [s.lon, s.lat] },
      properties: {
        stopped: s.stopped ? 1 : 0,
        hasData: s.has_data ? 1 : 0,
        label: s.label || "Signalized intersection",
        wait: Math.round(s.wait_s),
        arrive: fmtClock(s.arrive_epoch),
      },
    })),
  };
}

function pinElement(letter: "A" | "B"): HTMLDivElement {
  const el = document.createElement("div");
  el.className = `map-pin map-pin--${letter}`;
  // Static markup only (the letter is a constant), so innerHTML is safe here.
  el.innerHTML =
    '<svg viewBox="0 0 30 40" width="30" height="40" aria-hidden="true">' +
    '<path d="M15 38.5C15 38.5 27.5 25 27.5 14a12.5 12.5 0 0 0-25 0C2.5 25 15 38.5 15 38.5Z" fill="currentColor" stroke="#fff" stroke-width="2.5"/>' +
    `<text x="15" y="19" text-anchor="middle" font-size="13" font-weight="700" fill="#fff">${letter}</text>` +
    "</svg>";
  el.setAttribute("aria-label", letter === "A" ? "Start point" : "Destination point");
  return el;
}

interface Props {
  from: Place | null;
  to: Place | null;
  result: RouteResponse | null;
  lights: LightsView;
  onMapClick: (lat: number, lon: number) => void;
  onPinDrag: (which: "from" | "to", lat: number, lon: number) => void;
}

export function MapView({ from, to, result, lights, onMapClick, onPinDrag }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<{ from: Marker | null; to: Marker | null }>({ from: null, to: null });
  const lastFitKey = useRef<string>("");
  const handlers = useRef({ onMapClick, onPinDrag });
  handlers.current = { onMapClick, onPinDrag };
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new MapLibreMap({
      container: containerRef.current,
      style: MAP_STYLE,
      center: SF_CENTER,
      zoom: 11.7,
      attributionControl: false,
    });
    mapRef.current = map;
    map.addControl(new AttributionControl({ compact: true }), "bottom-right");
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");

    map.on("load", () => {
      const firstSymbol = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
      for (const id of ["blind", "aware"]) {
        map.addSource(`${id}-route`, { type: "geojson", data: EMPTY as never });
      }
      map.addLayer(
        { id: "blind-casing", type: "line", source: "blind-route",
          layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": "#ffffff", "line-width": 8, "line-opacity": 0.9 } },
        firstSymbol,
      );
      map.addLayer(
        { id: "blind-line", type: "line", source: "blind-route",
          layout: { "line-join": "round", "line-cap": "butt" },
          paint: { "line-color": "#64748b", "line-width": 4, "line-dasharray": [1.6, 1.4] } },
        firstSymbol,
      );
      map.addLayer(
        { id: "aware-casing", type: "line", source: "aware-route",
          layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": "#ffffff", "line-width": 10, "line-opacity": 0.95 } },
        firstSymbol,
      );
      map.addLayer(
        { id: "aware-line", type: "line", source: "aware-route",
          layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": "#2563eb", "line-width": 5.5 } },
        firstSymbol,
      );

      map.addSource("signals", { type: "geojson", data: EMPTY as never });
      map.addLayer({
        id: "signals",
        type: "circle",
        source: "signals",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 2.5, 13, 4.5, 16, 8],
          "circle-color": [
            "case",
            ["==", ["get", "hasData"], 0], "#94a3b8",
            ["==", ["get", "stopped"], 1], "#dc2626",
            "#16a34a",
          ],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
        },
      });

      const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 10, className: "signal-popup" });
      map.on("mousemove", "signals", (e) => {
        const f = e.features?.[0];
        if (!f) return;
        map.getCanvas().style.cursor = "pointer";
        const p = f.properties as { label: string; stopped: number; hasData: number; wait: number; arrive: string };
        const el = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = p.label;
        const detail = document.createElement("div");
        detail.textContent =
          Number(p.hasData) === 0
            ? "No signal data"
            : Number(p.stopped) === 1
              ? `Red on arrival, waits ${p.wait} s`
              : "Green on arrival";
        const when = document.createElement("div");
        when.className = "signal-popup__muted";
        when.textContent = `Reached at ${p.arrive}`;
        el.append(title, detail, when);
        popup.setLngLat((f.geometry as unknown as { coordinates: [number, number] }).coordinates).setDOMContent(el).addTo(map);
      });
      map.on("mouseleave", "signals", () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });

      map.on("click", (e) => handlers.current.onMapClick(e.lngLat.lat, e.lngLat.lng));
      setReady(true);
    });

    return () => {
      markersRef.current.from?.remove();
      markersRef.current.to?.remove();
      markersRef.current = { from: null, to: null };
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const sync = (which: "from" | "to", place: Place | null, letter: "A" | "B") => {
      const existing = markersRef.current[which];
      if (!place) {
        existing?.remove();
        markersRef.current[which] = null;
        return;
      }
      if (existing) {
        existing.setLngLat([place.lon, place.lat]);
        return;
      }
      const marker = new Marker({ element: pinElement(letter), anchor: "bottom", draggable: true })
        .setLngLat([place.lon, place.lat])
        .addTo(map);
      marker.on("dragend", () => {
        const ll = marker.getLngLat();
        handlers.current.onPinDrag(which, ll.lat, ll.lng);
      });
      markersRef.current[which] = marker;
    };
    sync("from", from, "A");
    sync("to", to, "B");
  }, [from, to, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const set = (id: string, data: FeatureCollection) => (map.getSource(id) as GeoJSONSource).setData(data as never);

    // When both routes are identical, draw the path once (as the Rheo route) rather than stacking them.
    set("blind-route", lineData(result && !result.comparison.same_route ? result.blind : null));
    set("aware-route", lineData(result?.aware ?? null));
    const lit = lights === "off" || !result ? null : lights === "aware" ? result.aware : result.blind;
    set("signals", signalData(lit));
  }, [result, lights, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !result) return;
    const key = `${result.origin.snapped.lat},${result.origin.snapped.lon}|${result.destination.snapped.lat},${result.destination.snapped.lon}`;
    if (key === lastFitKey.current) return;
    lastFitKey.current = key;
    const bounds = new LngLatBounds();
    for (const c of [...result.blind.geometry, ...result.aware.geometry]) bounds.extend(c as [number, number]);
    const desktop = window.matchMedia("(min-width: 821px)").matches;
    map.fitBounds(bounds, {
      padding: desktop ? { top: 70, bottom: 70, left: 460, right: 70 } : { top: 70, bottom: Math.round(window.innerHeight * 0.6), left: 40, right: 40 },
      duration: 700,
      maxZoom: 15,
    });
  }, [result, ready]);

  useEffect(() => {
    if (!from && !to) lastFitKey.current = "";
  }, [from, to]);

  return <div ref={containerRef} className="map" />;
}
