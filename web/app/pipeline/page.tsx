"use client";
import { useEffect, useState } from "react";
import { ArrowDown, ArrowRight, Archive, CheckCircle2, CloudSun, Globe, Loader2, Medal, ShieldCheck, XCircle } from "lucide-react";

interface Run {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: "running" | "success" | "failed";
  rows_ingested: number;
  rows_rejected: number;
  error: string | null;
}

const STAGES = [
  { Icon: CloudSun, name: "Open-Meteo", role: "Source", color: "#22d3ee", text: "Weather, air quality and sea forecasts, fetched every hour." },
  { Icon: Archive, name: "Bronze", role: "Raw", color: "#cd7f32", text: "API responses saved untouched as JSON in the repo, once a day." },
  { Icon: ShieldCheck, name: "Silver", role: "Clean", color: "#c0c8d4", text: "Validated with Pydantic. Bad rows rejected, duplicates dropped, UTC times, upserted into Neon." },
  { Icon: Medal, name: "Gold", role: "Models", color: "#fbbf24", text: "SQL views: daily averages, rankings, rain alerts and beach scores." },
  { Icon: Globe, name: "This site", role: "Serve", color: "#22d3ee", text: "Next.js on Vercel reads the gold views." },
];

const manila = (iso: string) =>
  new Date(iso).toLocaleString("en-PH", { timeZone: "Asia/Manila", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

function ago(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}

const seconds = (r: Run) =>
  r.finished_at ? `${Math.round((new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()) / 1000)} s` : "–";

export default function PipelinePage() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [latest, setLatest] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/pipeline")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: { runs: Run[]; latestObservation: string | null }) => { setRuns(d.runs); setLatest(d.latestObservation); })
      .catch((e: Error) => setError(`Could not load pipeline status (${e.message}). Try again in a minute.`));
  }, []);

  const last = runs?.[0];
  const succeeded = runs?.filter((r) => r.status === "success").length ?? 0;
  const total = last ? last.rows_ingested + last.rows_rejected : 0;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Pipeline</h1>
          <p className="text-sm text-[var(--muted)]">How the data gets from Open-Meteo to this page.</p>
        </div>
        {last && <StatusBadge status={last.status} large />}
      </header>

      {error && <p role="alert" className="glass rounded-2xl p-4 text-sm">{error}</p>}

      <section aria-label="Architecture" className="space-y-3">
        <ol className="flex flex-col gap-2 lg:flex-row lg:items-stretch">
          {STAGES.map(({ Icon, name, role, color, text }, i) => (
            <li key={name} className="contents">
              <div className="glass flex-1 rounded-2xl p-4" style={{ borderColor: `${color}55` }}>
                <span className="inline-flex items-center gap-2 font-semibold" style={{ color }}>
                  <Icon size={18} aria-hidden />{name}
                </span>
                <span className="ml-2 text-xs text-[var(--muted)]">{role}</span>
                <p className="mt-1 text-sm text-[var(--muted)]">{text}</p>
              </div>
              {i < STAGES.length - 1 && (
                <>
                  <ArrowDown size={18} className="mx-auto text-[var(--muted)] lg:hidden" aria-hidden />
                  <ArrowRight size={18} className="hidden shrink-0 self-center text-[var(--muted)] lg:block" aria-hidden />
                </>
              )}
            </li>
          ))}
        </ol>
        <p className="text-sm text-[var(--muted)]">
          GitHub Actions runs everything every hour. A quality gate blocks a batch that is stale, too empty or missing
          too many places, so bad data never reaches the site.
        </p>
      </section>

      <section aria-label="Latest run" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {!runs && !error
          ? [0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-24 rounded-2xl" />)
          : last && (
            <>
              <Card label="Last run" value={ago(last.started_at)} sub={`${manila(last.started_at)} Manila time`} />
              <Card label="Rows ingested" value={last.rows_ingested.toLocaleString()} />
              <Card label="Rows rejected" value={last.rows_rejected.toLocaleString()}
                sub={total ? `${((last.rows_rejected / total) * 100).toFixed(1)}% of rows` : undefined} />
              <Card label="Newest data" value={latest ? ago(latest) : "No data"} sub={`${succeeded} of ${runs!.length} recent runs succeeded`} />
            </>
          )}
      </section>

      <section aria-label="Run history" className="space-y-3">
        <h2 className="text-lg font-semibold">Run history</h2>
        {runs && runs.length === 0 && <p className="glass rounded-2xl p-4 text-sm">No runs recorded yet.</p>}
        {runs && runs.length > 0 && (
          <div className="glass overflow-x-auto rounded-2xl">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-[var(--muted)]">
                <tr>{["Run", "Started (Manila)", "Status", "Ingested", "Rejected", "Took", "Note"].map((h) => (
                  <th key={h} scope="col" className="px-4 py-3 font-medium">{h}</th>
                ))}</tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className="border-t border-[var(--border)] transition-colors hover:bg-[var(--card)]">
                    <td className="px-4 py-3">#{r.id}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{manila(r.started_at)}</td>
                    <td className="px-4 py-3"><StatusBadge status={r.status} /></td>
                    <td className="px-4 py-3">{r.rows_ingested.toLocaleString()}</td>
                    <td className="px-4 py-3">{r.rows_rejected.toLocaleString()}</td>
                    <td className="px-4 py-3">{seconds(r)}</td>
                    <td className="max-w-[260px] truncate px-4 py-3 text-[var(--muted)]" title={r.error ?? undefined}>{r.error ?? "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function StatusBadge({ status, large = false }: { status: Run["status"]; large?: boolean }) {
  const cfg = {
    success: { Icon: CheckCircle2, color: "#34d399", label: "Healthy" },
    failed: { Icon: XCircle, color: "#ef4444", label: "Failed" },
    running: { Icon: Loader2, color: "#22d3ee", label: "Running" },
  }[status];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold ${large ? "px-3 py-1.5 text-sm" : "px-2.5 py-1 text-xs"}`}
      style={{ background: `${cfg.color}26`, color: cfg.color }}>
      <cfg.Icon size={large ? 16 : 14} aria-hidden className={status === "running" ? "animate-spin" : undefined} />
      {status === "success" && !large ? "Success" : cfg.label}
    </span>
  );
}

function Card({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="glass rounded-2xl p-4">
      <p className="text-sm text-[var(--muted)]">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {sub && <p className="text-sm text-[var(--muted)]">{sub}</p>}
    </div>
  );
}
