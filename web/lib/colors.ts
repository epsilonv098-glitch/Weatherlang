export type Mode = "aqi" | "temp" | "heat";

export interface Loc {
  location: string;
  area_type: "metro" | "mainland" | "tourist";
  lat: number;
  lon: number;
  observed_at: string;
  temperature_c: number | null;
  apparent_temp_c: number | null;
  us_aqi: number | null;
  heat_index_category: "Normal" | "Caution" | "Danger" | null;
  rain_next_6h_mm: number | null;
}

const NONE = "#64748b";
/** The page accent shifts with what you are looking at: heat is orange, air is amber. */
export const ACCENT: Record<Mode, string> = { temp: "#f97316", heat: "#f97316", aqi: "#f59e0b" };
export const RAIN_ACCENT = "#22d3ee";

/** US AQI bands. */
export function aqiColor(aqi: number | null): string {
  if (aqi === null) return NONE;
  if (aqi <= 50) return "#34d399";
  if (aqi <= 100) return "#fbbf24";
  if (aqi <= 150) return "#fb923c";
  if (aqi <= 200) return "#ef4444";
  return "#a855f7";
}

const HEAT: Record<string, string> = { Normal: "#2dd4bf", Caution: "#fbbf24", Danger: "#ef4444" };

export function markerColor(mode: Mode, l: Loc): string {
  if (mode === "aqi") return aqiColor(l.us_aqi);
  if (mode === "heat") return l.heat_index_category ? HEAT[l.heat_index_category] : NONE;
  if (l.temperature_c === null) return NONE;
  const t = Math.min(1, Math.max(0, (l.temperature_c - 24) / 14)); // 24C blue ... 38C red
  return `hsl(${Math.round(200 * (1 - t))} 85% 55%)`;
}

export function valueLabel(mode: Mode, l: Loc): string {
  if (mode === "aqi") return l.us_aqi === null ? "No data" : `AQI ${l.us_aqi}`;
  if (mode === "heat") return l.heat_index_category ?? "No data";
  return l.temperature_c === null ? "No data" : `${l.temperature_c.toFixed(1)}°C`;
}

export const manilaTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-PH", { timeZone: "Asia/Manila", hour: "numeric", minute: "2-digit" });
