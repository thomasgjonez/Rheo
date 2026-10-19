export function fmtDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return rem === 0 ? `${m} min` : `${m} min ${rem} s`;
}

export function fmtClock(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function fmtMiles(meters: number): string {
  return `${(meters / 1609.344).toFixed(1)} mi`;
}

export function pinnedLabel(lat: number, lon: number): string {
  return `Pinned location (${lat.toFixed(4)}, ${lon.toFixed(4)})`;
}
