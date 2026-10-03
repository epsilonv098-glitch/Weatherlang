"use client";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export const LINE_COLORS = ["#f97316", "#22d3ee", "#a78bfa"];

export interface Series {
  name: string;
  points: { t: number; [metric: string]: number | null }[];
}

const manila = (ms: number, o: Intl.DateTimeFormatOptions) =>
  new Date(ms).toLocaleString("en-PH", { timeZone: "Asia/Manila", ...o });
const AXIS = { stroke: "var(--muted)", fontSize: 11, tickLine: false, axisLine: false } as const;

/** One line per place on a shared time axis. */
export default function CompareChart({ series, metric, unit, step = false }: {
  series: Series[]; metric: string; unit: string; step?: boolean;
}) {
  // Merge the per-place series into rows keyed by timestamp: { t, "Cebu City": 28.1, "Oslob": 27.4 }
  const rows = new Map<number, Record<string, number | null>>();
  for (const s of series) {
    for (const p of s.points) {
      const row = rows.get(p.t) ?? { t: p.t };
      row[s.name] = p[metric];
      rows.set(p.t, row);
    }
  }
  const data = [...rows.values()].sort((a, b) => (a.t as number) - (b.t as number));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -14 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickCount={5}
          tickFormatter={(t: number) => manila(t, { weekday: "short", day: "numeric" })} {...AXIS} />
        <YAxis domain={["auto", "auto"]} width={44} {...AXIS} />
        {/* `as never`: Recharts' formatter types vary by version; runtime behaviour is fine. */}
        <Tooltip contentStyle={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 12, fontSize: 12 }}
          labelFormatter={((t: unknown) => manila(Number(t), { weekday: "short", hour: "numeric", minute: "2-digit" })) as never}
          formatter={((v: unknown) => `${v} ${unit}`) as never} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {series.map((s, i) => (
          <Line key={s.name} dataKey={s.name} stroke={LINE_COLORS[i % LINE_COLORS.length]} strokeWidth={2}
            type={step ? "stepAfter" : "monotone"} dot={false} connectNulls />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
