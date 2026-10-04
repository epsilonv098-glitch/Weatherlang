import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";

export const dynamic = "force-dynamic";

/** Recent pipeline runs plus the age of the newest stored observation. */
export async function GET() {
  try {
    const sql = getSql();
    const [runs, fresh] = await Promise.all([
      // Error text is public on this page, so only a short prefix is exposed.
      sql`SELECT id, started_at, finished_at, status, rows_ingested, rows_rejected,
                 left(error, 140) AS error
          FROM pipeline_runs ORDER BY id DESC LIMIT 20`,
      sql`SELECT max(observed_at) AS latest FROM observations_silver WHERE observed_at <= now()`,
    ]);
    return NextResponse.json(
      { runs, latestObservation: fresh[0]?.latest ?? null },
      { headers: { "Cache-Control": "s-maxage=60, stale-while-revalidate=120" } },
    );
  } catch (err) {
    console.error("GET /api/pipeline failed", err);
    return NextResponse.json({ error: "Could not load pipeline status" }, { status: 500 });
  }
}
