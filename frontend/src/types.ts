export interface LatLon {
  lat: number;
  lon: number;
}

export interface Place extends LatLon {
  label: string;
}

export interface SignalEvent {
  id: number;
  label: string;
  lat: number;
  lon: number;
  arrive_epoch: number;
  wait_s: number;
  stopped: boolean;
  has_data: boolean;
}

export interface RouteSummary {
  geometry: [number, number][]; // [lon, lat]
  distance_m: number;
  drive_time_s: number;
  wait_s: number;
  total_time_s: number;
  arrival_epoch: number;
  stops: number;
  signals_on_route: number;
  signals_with_data: number;
  signals: SignalEvent[];
}

export interface Snap {
  requested: LatLon;
  snapped: LatLon;
  snap_distance_m: number;
}

export type SpatMode = "simulated" | "live";

export interface RouteResponse {
  depart_epoch: number;
  spat: { mode: SpatMode; label: string; is_simulated: boolean; connected: boolean };
  origin: Snap;
  destination: Snap;
  blind: RouteSummary;
  aware: RouteSummary;
  comparison: {
    same_route: boolean;
    time_saved_s: number;
    wait_saved_s: number;
    stops_avoided: number;
  };
}

export interface GeocodeResponse {
  results: Place[];
  error: string | null;
}

export type LightsView = "aware" | "blind" | "off";
