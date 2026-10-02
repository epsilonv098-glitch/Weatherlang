"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { MotionConfig, motion } from "framer-motion";
import { CloudRain, Flame, Wind } from "lucide-react";
import { ACCENT, RAIN_ACCENT, aqiColor, manilaTime, type Loc, type Mode } from "@/lib/colors";

const ConditionsMap = dynamic(() => import("@/components/ConditionsMap"), {
  ssr: false,
  loading: () => <div className="skeleton h-[55vh] min-h-[340px] rounded-2xl" />,
});

const MODES: { id: Mode; label: string }[] = [
  { id: "aqi", label: "Air quality" },
  { id: "temp", label: "Temperature" },
  { id: "heat", label: "Heat index" },
];

export default function Home() {
  const [locations, setLocations] = useState<Loc[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("aqi");

  useEffect(() => {
    fetch("/api/conditions")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => setLocations(d.locations))
      .catch((e) => setError(`Could not load live data (${e.message}). Try again in a minute.`));
  }, []);

  const top = useMemo(() => {
    if (!locations?.length) return null;
    const by = (f: (l: Loc) => number | null, dir: 1 | -1) =>
      locations.filter((l) => f(l) !== null).sort((a, b) => dir * (f(a)! - f(b)!))[0];
    return {
      hottest: by((l) => l.apparent_temp_c, -1),
      cleanest: by((l) => l.us_aqi, 1),
      rainiest: by((l) => l.rain_next_6h_mm, -1),
      updated: locations.map((l) => l.observed_at).sort().at(-1)!,
    };
  }, [locations]);

  const rain = top?.rainiest?.rain_next_6h_mm ?? 0;

  return (
    <MotionConfig reducedMotion="user">
      <div style={{ "--accent": ACCENT[mode] } as React.CSSProperties} className="space-y-5">
        {error && <p role="alert" className="glass rounded-2xl p-4 text-sm">{error}</p>}

        <section aria-label="Highlights" className="grid gap-3 sm:grid-cols-3">
          {!top && !error
            ? [0, 1, 2].map((i) => <div key={i} className="skeleton h-24 rounded-2xl" />)
            : top && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5 }} className="contents">
                <Highlight Icon={Flame} color={ACCENT.heat} title="Feels hottest"
                  main={top.hottest?.location} sub={top.hottest?.apparent_temp_c != null ? `feels like ${top.hottest.apparent_temp_c.toFixed(1)}°C` : "no data"} />
                <Highlight Icon={Wind} color={aqiColor(top.cleanest?.us_aqi ?? null)} title="Cleanest air"
                  main={top.cleanest?.location} sub={top.cleanest?.us_aqi != null ? `US AQI ${top.cleanest.us_aqi}` : "no data"} />
                <Highlight Icon={CloudRain} color={RAIN_ACCENT} title="Rain in the next 6 hours"
                  main={rain >= 0.5 ? top.rainiest?.location : "Dry everywhere"} sub={rain >= 0.5 ? `${rain.toFixed(1)} mm expected` : "less than 0.5 mm forecast"} />
              </motion.div>
            )}
        </section>

        <section aria-label="Map" className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div role="group" aria-label="Color the map by" className="glass inline-flex rounded-2xl p-1">
              {MODES.map((m) => (
                <button key={m.id} aria-pressed={mode === m.id} onClick={() => setMode(m.id)}
                  className={`rounded-xl px-3 py-2 text-sm transition-colors ${mode === m.id ? "bg-[var(--accent)] font-semibold text-black" : "text-[var(--muted)] hover:text-inherit"}`}>
                  {m.label}
                </button>
              ))}
            </div>
            {top && <p className="text-sm text-[var(--muted)]">Updated {manilaTime(top.updated)} Manila time</p>}
          </div>
          {locations ? <ConditionsMap locations={locations} mode={mode} /> : <div className="skeleton h-[55vh] min-h-[340px] rounded-2xl" />}
        </section>
      </div>
    </MotionConfig>
  );
}

function Highlight({ Icon, color, title, main, sub }: {
  Icon: typeof Flame; color: string; title: string; main?: string; sub: string;
}) {
  return (
    <div className="glass flex items-center gap-4 rounded-2xl p-4">
      <span className="rounded-xl p-2.5" style={{ background: `${color}26`, color }}><Icon size={22} aria-hidden /></span>
      <div className="min-w-0">
        <p className="text-sm text-[var(--muted)]">{title}</p>
        <p className="truncate text-lg font-semibold">{main ?? "No data"}</p>
        <p className="text-sm text-[var(--muted)]">{sub}</p>
      </div>
    </div>
  );
}
