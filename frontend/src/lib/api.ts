import type { GeocodeResponse, LatLon, RouteResponse, SpatMode } from "../types";

export class ApiError extends Error {}

export async function fetchRoute(
  origin: LatLon,
  destination: LatLon,
  departEpoch: number,
  spatMode: SpatMode,
  signal: AbortSignal,
): Promise<RouteResponse> {
  const res = await fetch("/api/route", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      origin: { lat: origin.lat, lon: origin.lon },
      destination: { lat: destination.lat, lon: destination.lon },
      depart_epoch: departEpoch,
      spat_mode: spatMode,
    }),
    signal,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body && typeof body.detail === "string" ? body.detail : null;
    throw new ApiError(detail ?? "Something went wrong while routing that trip.");
  }
  return res.json();
}

export async function searchPlaces(query: string, signal: AbortSignal): Promise<GeocodeResponse> {
  const res = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`, { signal });
  if (!res.ok) throw new ApiError("Address search is unavailable.");
  return res.json();
}
