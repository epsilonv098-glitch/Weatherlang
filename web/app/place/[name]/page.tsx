"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, CloudRain, Droplets, Gauge, Thermometer, Waves, Wind } from "lucide-react";
import { aqiColor, manilaTime, markerColor, type Loc } from "@/lib/colors";
import { CompareBars, RainBars, Trend } from "@/components/PlaceCharts";

interface Place {
  location: string;
  area_type: string;
  observed_at: string;
  temperature_c: number | null;
  apparent_temp_c: number | null;
  humidity_pct: number | null;
  wind_speed_kmh: number | null;
  pm2_5: number | null;
  us_aqi: number | null;
  heat_index_category: "Normal" | "Caution" | "Danger" | null;
  rain_next_6h_mm: number | null;
}
interface Rank { location: string; aqi: number | null; aqiRank: number; heatRank: number; rainRank: number }
interface Beach { beach_score: number | null; verdict: string; wave_height_m: number | null; wave_period_s: number | null }
interface Data {
  place: Place;
  beach: Beach | null;
  hourly: Record<string, number | null>[];
  daily: { date: string; rain: number | null }[];
  ranks: Rank[];
}

/** Heat -> orange, rain -> cyan, poor air -> amber, otherwise calm cyan. */
function accentFor(p: Place): string {
  if (p.heat_index_category === "Caution" || p.heat_index_category === "Danger") return "#f97316";
  if ((p.rain_next_6h_mm ?? 0) >= 1) return "#22d3ee";
  if ((p.us_aqi ?? 0) > 100) return "#f59e0b";
  return "#22d3ee";
}

function aqiLabel(aqi: number | null): string {
  if (aqi === null) return "No data";
  if (aqi <= 50) return "Good";
  if (aqi <= 100) return "Moderate";
  if (aqi <= 150) return "Unhealthy for sensitive groups";
  return aqi <= 200 ? "Unhealthy" : "Very unhealthy";
}

export default function PlacePage() {
  const { name: rawName } = useParams<{ name: string }>();
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/place/${rawName}`)
      .then(async (r) => {
        if (r.status === 404) throw new Error("We don't have data for that place.");
        if (!r.ok) throw new Error("Could not load this place. Try again in a minute.");
        return r.json();
      })
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [rawName]);

  const back = (
    <Link href="/" className="inline-flex items-center gap-1 text-sm text-[var(--muted)] hover:text-inherit">
      <ArrowLeft size={16} aria-hidden /> All places
    </Link>
  );

  if (error) return <div className="space-y-4">{back}<p role="alert" className="glass rounded-2xl p-4">{error}</p></div>;
  if (!data) {
    return (
      <div className="space-y-4">
        {back}
        <div className="skeleton h-16 rounded-2xl" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="skeleton h-24 rounded-2xl" />)}
        </div>
        <div className="skeleton h-48 rounded-2xl" />
      </div>
    );
  }

  const { place: p, beach, hourly, daily, ranks } = data;
  const accent = accentFor(p);
  const heatColor = markerColor("heat", { heat_index_category: p.heat_index_category } as Loc);
  const me = ranks.find((r) => r.location === p.location);
  const total = ranks.length;
  const rain = p.rain_next_6h_mm;
  const fmt = (v: number | null, unit: string, d = 1) => (v === null ? "No data" : `${v.toFixed(d)}${unit}`);

  return (
    <div style={{ "--accent": accent } as React.CSSProperties} className="space-y-6">
      {back}
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{p.location}</h1>
          <p className="text-sm text-[var(--muted)]">
            {p.area_type === "tourist" ? "Coastal and tourist area" : p.area_type === "metro" ? "Metro Cebu" : "Mainland Cebu"}
            {" · "}Updated {manilaTime(p.observed_at)} Manila time
          </p>
        </div>
        <span className="rounded-full px-3 py-1.5 text-sm font-semibold" style={{ background: `${heatColor}26`, color: heatColor }}>
          Heat: {p.heat_index_category ?? "No data"}
          {p.apparent_temp_c !== null && ` · feels like ${p.apparent_temp_c.toFixed(1)}°C`}
        </span>
      </header>

      <section aria-label="Live conditions" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat Icon={Thermometer} label="Temperature" value={fmt(p.temperature_c, "°C")} />
        <Stat Icon={Droplets} label="Humidity" value={fmt(p.humidity_pct, "%", 0)} />
        <Stat Icon={Wind} label="Wind" value={fmt(p.wind_speed_kmh, " km/h", 0)} />
        <Stat Icon={Gauge} label="Air quality (US AQI)" value={p.us_aqi === null ? "No data" : String(p.us_aqi)}
          sub={aqiLabel(p.us_aqi)} color={aqiColor(p.us_aqi)} />
        <Stat Icon={Gauge} label="PM2.5" value={fmt(p.pm2_5, " µg/m³")} />
        <Stat Icon={CloudRain} label="Rain, next 6 hours" value={rain === null ? "No data" : `${rain.toFixed(1)} mm`}
          sub={rain !== null && rain < 0.5 ? "Dry" : undefined} color="#22d3ee" />
        <Stat Icon={Waves} label="Waves" color="#22d3ee"
          value={beach?.wave_height_m == null ? "No data" : `${beach.wave_height_m.toFixed(1)} m`}
          sub={beach?.wave_period_s ? `${beach.wave_period_s.toFixed(0)} s apart` : undefined} />
        <Stat Icon={Waves} label="Beach score" color="#22d3ee"
          value={beach?.beach_score == null ? "No data" : `${beach.beach_score}/100`} sub={beach?.verdict} />
      </section>

      <section aria-label="Last 7 days" className="space-y-3">
        <h2 className="text-lg font-semibold">Last 7 days</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <ChartCard title="Temperature (°C)"><Trend data={hourly} dataKey="temp" color="#f97316" unit="°C" /></ChartCard>
          <ChartCard title="Air quality (US AQI)"><Trend data={hourly} dataKey="aqi" color="#f59e0b" unit="AQI" /></ChartCard>
          <ChartCard title="Humidity (%)"><Trend data={hourly} dataKey="humidity" color="#22d3ee" unit="%" /></ChartCard>
          <ChartCard title="Rainfall per day (mm)"><RainBars data={daily} /></ChartCard>
        </div>
      </section>

      <section aria-label="Comparison" className="space-y-3">
        <h2 className="text-lg font-semibold">How {p.location} compares</h2>
        {me && (
          <div className="flex flex-wrap gap-2 text-sm">
            <Chip>Cleanest air: #{me.aqiRank} of {total}</Chip>
            <Chip>Hottest: #{me.heatRank} of {total}</Chip>
            <Chip>Wettest (24h): #{me.rainRank} of {total}</Chip>
          </div>
        )}
        <ChartCard title="Average AQI, last 24 hours (lower is cleaner)">
          <CompareBars data={ranks} current={p.location} accent={accent} />
        </ChartCard>
      </section>
    </div>
  );
}

function Stat({ Icon, label, value, sub, color }: {
  Icon: typeof Wind; label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="glass rounded-2xl p-4 transition-transform hover:-translate-y-0.5">
      <p className="flex items-center gap-2 text-sm text-[var(--muted)]"><Icon size={16} aria-hidden />{label}</p>
      <p className="mt-1 text-2xl font-semibold" style={color ? { color } : undefined}>{value}</p>
      {sub && <p className="text-sm text-[var(--muted)]">{sub}</p>}
    </div>
  );
}

const ChartCard = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div className="glass rounded-2xl p-4">
    <h3 className="mb-2 text-sm text-[var(--muted)]">{title}</h3>
    {children}
  </div>
);

const Chip = ({ children }: { children: React.ReactNode }) => (
  <span className="glass rounded-full px-3 py-1.5">{children}</span>
);
