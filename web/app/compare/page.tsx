"use client";
import { useEffect, useState } from "react";
import CompareChart, { LINE_COLORS, type Series } from "@/components/CompareChart";

const MAX = 3;
const METRICS = [
  { id: "temp", label: "Temperature", unit: "°C", accent: "#f97316", step: false },
  { id: "aqi", label: "Air quality", unit: "AQI", accent: "#f59e0b", step: false },
  { id: "humidity", label: "Humidity", unit: "%", accent: "#22d3ee", step: false },
  { id: "rain", label: "Rain", unit: "mm/h", accent: "#22d3ee", step: true },
] as const;

export default function ComparePage() {
  const [names, setNames] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [metric, setMetric] = useState<(typeof METRICS)[number]>(METRICS[0]);
  const [series, setSeries] = useState<Series[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Place list (reuses the landing-page endpoint).
  useEffect(() => {
    fetch("/api/conditions")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: { locations: { location: string }[] }) => {
        const list = d.locations.map((l) => l.location).sort();
        const pick = ["Cebu City", "Oslob"].filter((n) => list.includes(n));
        setNames(list);
        setSelected(pick.length === 2 ? pick : list.slice(0, 2));
      })
      .catch((e: Error) => setError(`Could not load places (${e.message}). Try again in a minute.`));
  }, []);

  // History for the current selection.
  useEffect(() => {
    if (selected.length === 0) return;
    let cancelled = false;
    setSeries(null);
    fetch(`/api/compare?places=${encodeURIComponent(selected.join(","))}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: { series: Series[] }) => { if (!cancelled) { setSeries(d.series); setError(null); } })
      .catch((e: Error) => { if (!cancelled) setError(`Could not load the comparison (${e.message}).`); });
    return () => { cancelled = true; };
  }, [selected]);

  const toggle = (n: string) =>
    setSelected((cur) => (cur.includes(n) ? cur.filter((x) => x !== n) : cur.length < MAX ? [...cur, n] : cur));
  const empty = series?.every((s) => s.points.length === 0);

  return (
    <div style={{ "--accent": metric.accent } as React.CSSProperties} className="space-y-5">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Compare places</h1>
        <p className="text-sm text-[var(--muted)]">Pick up to {MAX} places and overlay the last 7 days.</p>
      </header>

      {error && <p role="alert" className="glass rounded-2xl p-4 text-sm">{error}</p>}

      <div role="group" aria-label="Places to compare" className="flex flex-wrap gap-2">
        {names.length === 0 && !error && [0, 1, 2, 3, 4].map((i) => <div key={i} className="skeleton h-9 w-24 rounded-full" />)}
        {names.map((n) => {
          const idx = selected.indexOf(n);
          const on = idx >= 0;
          const locked = !on && selected.length >= MAX;
          return (
            <button key={n} aria-pressed={on} aria-disabled={locked} onClick={() => !locked && toggle(n)}
              className={`glass flex items-center gap-2 rounded-full px-3 py-1.5 text-sm transition-colors ${locked ? "opacity-40" : "hover:bg-[var(--card)]"}`}
              style={on ? { borderColor: LINE_COLORS[idx] } : undefined}>
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: on ? LINE_COLORS[idx] : "var(--border)" }} aria-hidden />
              {n}
            </button>
          );
        })}
      </div>

      <div role="group" aria-label="Measure" className="glass inline-flex flex-wrap rounded-2xl p-1">
        {METRICS.map((m) => (
          <button key={m.id} aria-pressed={metric.id === m.id} onClick={() => setMetric(m)}
            className={`rounded-xl px-3 py-2 text-sm transition-colors ${metric.id === m.id ? "bg-[var(--accent)] font-semibold text-black" : "text-[var(--muted)] hover:text-inherit"}`}>
            {m.label}
          </button>
        ))}
      </div>

      <section aria-label="Comparison chart" className="glass rounded-2xl p-4">
        <h2 className="mb-2 text-sm text-[var(--muted)]">{metric.label} ({metric.unit}), last 7 days</h2>
        {selected.length === 0 ? (
          <p className="py-16 text-center text-[var(--muted)]">Pick a place above to start.</p>
        ) : !series ? (
          <div className="skeleton h-[300px] rounded-xl" />
        ) : empty ? (
          <p className="py-16 text-center text-[var(--muted)]">No data for this selection yet.</p>
        ) : (
          <CompareChart series={series} metric={metric.id} unit={metric.unit} step={metric.step} />
        )}
      </section>
    </div>
  );
}
