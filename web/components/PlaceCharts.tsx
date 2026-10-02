"use client";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

const manila = (ms: number, o: Intl.DateTimeFormatOptions) =>
  new Date(ms).toLocaleString("en-PH", { timeZone: "Asia/Manila", ...o });

const TIP = { background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 12, fontSize: 12 };
const AXIS = { stroke: "var(--muted)", fontSize: 11, tickLine: false, axisLine: false } as const;
const MARGIN = { top: 6, right: 8, bottom: 0, left: -14 };

/** Smooth area chart over time (hourly points, x axis in Manila days). */
export function Trend({ data, dataKey, color, unit }: {
  data: Record<string, number | null>[]; dataKey: string; color: string; unit: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={170}>
      <AreaChart data={data} margin={MARGIN}>
        <defs>
          <linearGradient id={`fill-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.35} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickCount={4}
          tickFormatter={(t: number) => manila(t, { weekday: "short", day: "numeric" })} {...AXIS} />
        <YAxis domain={["auto", "auto"]} width={44} {...AXIS} />
        {/* `as never`: Recharts' formatter types are strict across versions; runtime is fine. */}
        <Tooltip contentStyle={TIP}
          labelFormatter={((t: unknown) => manila(Number(t), { weekday: "short", hour: "numeric", minute: "2-digit" })) as never}
          formatter={((v: unknown) => [`${v} ${unit}`, ""]) as never} />
        <Area type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2}
          fill={`url(#fill-${dataKey})`} connectNulls />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** Daily rainfall totals as bars. `date` is a Manila calendar day, 'YYYY-MM-DD'. */
export function RainBars({ data }: { data: { date: string; rain: number | null }[] }) {
  return (
    <ResponsiveContainer width="100%" height={170}>
      <BarChart data={data} margin={MARGIN}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="date" {...AXIS}
          tickFormatter={(d: string) => new Date(`${d}T00:00:00Z`).toLocaleDateString("en-PH", { weekday: "short", timeZone: "UTC" })} />
        <YAxis width={44} {...AXIS} />
        <Tooltip contentStyle={TIP} cursor={{ fill: "var(--card)" }}
          formatter={((v: unknown) => [`${v} mm`, ""]) as never} />
        <Bar dataKey="rain" fill="#22d3ee" radius={[6, 6, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Horizontal bars of 24h average AQI for every place; the current place is highlighted. */
export function CompareBars({ data, current, accent }: {
  data: { location: string; aqi: number | null }[]; current: string; accent: string;
}) {
  const rows = data.filter((d) => d.aqi !== null).sort((a, b) => a.aqi! - b.aqi!);
  return (
    <ResponsiveContainer width="100%" height={rows.length * 26 + 16}>
      <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey="location" width={86} {...AXIS} />
        <Tooltip contentStyle={TIP} cursor={{ fill: "var(--card)" }}
          formatter={((v: unknown) => [`AQI ${v}`, ""]) as never} />
        <Bar dataKey="aqi" radius={[0, 6, 6, 0]}>
          {rows.map((r) => (
            <Cell key={r.location} fill={r.location === current ? accent : "rgba(144,171,189,0.35)"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
