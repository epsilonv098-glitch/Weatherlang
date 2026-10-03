import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";

export const dynamic = "force-dynamic";

/** Beach score, sea state and verdict for the tourist spots (gold_beach_score). */
export async function GET() {
  try {
    const sql = getSql();
    const beaches = await sql`
      SELECT b.location, b.beach_score, b.verdict, b.wave_height_m, b.wave_period_s,
             b.wind_speed_kmh, b.wind_gust_kmh, b.rain_next_6h_mm, b.marine_observed_at,
             c.temperature_c
      FROM gold_beach_score b
      LEFT JOIN gold_latest_conditions c ON c.location_id = b.location_id
      ORDER BY b.beach_score DESC NULLS LAST, b.location`;
    return NextResponse.json(
      { beaches },
      { headers: { "Cache-Control": "s-maxage=300, stale-while-revalidate=600" } },
    );
  } catch (err) {
    console.error("GET /api/beaches failed", err);
    return NextResponse.json({ error: "Could not load beach conditions" }, { status: 500 });
  }
}
