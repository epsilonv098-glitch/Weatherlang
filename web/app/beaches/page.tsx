"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { CloudRain, Thermometer, Waves, Wind } from "lucide-react";
import { manilaTime } from "@/lib/colors";

interface Beach {
  location: string;
  beach_score: number | null;
  verdict: string;
  wave_height_m: number | null;
  wave_period_s: number | null;
  wind_speed_kmh: number | null;
  wind_gust_kmh: number | null;
  rain_next_6h_mm: number | null;
  marine_observed_at: string | null;
  temperature_c: number | null;
}

const scoreColor = (s: number | null) =>
  s === null ? "#64748b" : s >= 80 ? "#34d399" : s >= 60 ? "#22d3ee" : s >= 40 ? "#fbbf24" : "#ef4444";

const seaState = (h: number | null) =>
  h === null ? "No wave data" : h < 0.3 ? "Calm" : h < 0.8 ? "Light chop" : h < 1.5 ? "Choppy" : "Rough";

export default function BeachesPage() {
  const [beaches, setBeaches] = useState<Beach[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/beaches")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => setBeaches(d.beaches))
      .catch((e: Error) => setError(`Could not load beach conditions (${e.message}). Try again in a minute.`));
  }, []);

  const best = beaches?.[0]?.beach_score != null ? beaches[0] : null;

  return (
    <div style={{ "--accent": "#22d3ee" } as React.CSSProperties} className="space-y-5">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Beaches</h1>
        <p className="text-sm text-[var(--muted)]">
          {best ? `Best right now: ${best.location} (${best.beach_score}/100)` : "Swim conditions at Cebu's tourist spots"}
        </p>
      </header>

      {error && <p role="alert" className="glass rounded-2xl p-4 text-sm">{error}</p>}
      {!beaches && !error && (
        <div className="grid gap-3 sm:grid-cols-2">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-56 rounded-2xl" />)}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {beaches?.map((b) => <BeachCard key={b.location} b={b} />)}
      </div>

      <p className="text-sm text-[var(--muted)]">
        The score is a simple guide built from waves (50%), wind (30%) and expected rain (20%). It is not a safety
        forecast. Follow lifeguards, local advisories and PAGASA warnings.
      </p>
    </div>
  );
}

function BeachCard({ b }: { b: Beach }) {
  const color = scoreColor(b.beach_score);
  return (
    <Link href={`/place/${encodeURIComponent(b.location)}`}
      className="glass block rounded-2xl p-5 transition-transform hover:-translate-y-0.5">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <h2 className="truncate text-xl font-semibold">{b.location}</h2>
          <p className="mt-1 text-lg font-medium" style={{ color }}>{b.verdict}</p>
          {b.marine_observed_at && (
            <p className="mt-1 text-xs text-[var(--muted)]">Sea data from {manilaTime(b.marine_observed_at)} Manila time</p>
          )}
        </div>
        <ScoreRing score={b.beach_score} color={color} />
      </div>
      <dl className="mt-4 space-y-2 text-sm">
        <Row Icon={Waves} label="Waves"
          value={b.wave_height_m === null ? "No data" : `${b.wave_height_m.toFixed(1)} m, ${seaState(b.wave_height_m).toLowerCase()}${b.wave_period_s ? ` (${b.wave_period_s.toFixed(0)} s apart)` : ""}`} />
        <Row Icon={Wind} label="Wind"
          value={b.wind_speed_kmh === null ? "No data" : `${b.wind_speed_kmh.toFixed(0)} km/h${b.wind_gust_kmh ? `, gusts ${b.wind_gust_kmh.toFixed(0)}` : ""}`} />
        <Row Icon={CloudRain} label="Rain, next 6h"
          value={b.rain_next_6h_mm === null ? "No data" : b.rain_next_6h_mm < 0.5 ? "Dry" : `${b.rain_next_6h_mm.toFixed(1)} mm`} />
        <Row Icon={Thermometer} label="Air"
          value={b.temperature_c === null ? "No data" : `${b.temperature_c.toFixed(1)}°C`} />
      </dl>
    </Link>
  );
}

function Row({ Icon, label, value }: { Icon: typeof Wind; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2">
      <dt className="flex w-32 shrink-0 items-center gap-2 text-[var(--muted)]"><Icon size={16} aria-hidden />{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

/** Circular 0-100 gauge; the arc animates in after mount. */
function ScoreRing({ score, color }: { score: number | null; color: string }) {
  const [shown, setShown] = useState(false);
  useEffect(() => { setShown(true); }, []);
  const r = 34;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - (shown && score !== null ? score / 100 : 0));
  return (
    <div className="relative h-[88px] w-[88px] shrink-0" role="img"
      aria-label={score === null ? "No beach score" : `Beach score ${score} out of 100`}>
      <svg viewBox="0 0 88 88" className="-rotate-90">
        <circle cx="44" cy="44" r={r} fill="none" stroke="var(--border)" strokeWidth="8" />
        <circle cx="44" cy="44" r={r} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={offset} style={{ transition: "stroke-dashoffset 900ms ease-out" }} />
      </svg>
      <span className="absolute inset-0 grid place-items-center text-2xl font-semibold">{score ?? "–"}</span>
    </div>
  );
}
