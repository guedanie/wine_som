// Distance from the user's zip centroid to the store, as sent by the backend
// (already rounded to 1 decimal). Whole miles drop the ".0"; null stays null
// so callers can skip the segment entirely.
export function formatMiles(distanceMiles) {
  const n = Number(distanceMiles);
  if (distanceMiles == null || !Number.isFinite(n)) return null;
  const rounded = n >= 10 ? Math.round(n) : Math.round(n * 10) / 10;
  return `${rounded} mi`;
}
