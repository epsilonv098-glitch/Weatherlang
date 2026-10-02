import { NextResponse } from "next/server";
import { getSql, num } from "@/lib/db";

export const dynamic = "force-dynamic";

/** Latest conditions per location plus the 6-hour rain outlook (gold views). */
export async function GET() {
  try {
    const sql = getSql();
    const rows = await sql`
      SELECT c.location, c.area_type, c.lat, c.lon, c.observed_at,
             c.temperature_c, c.apparent_temp_c, c.humidity_pct, c.wind_speed_kmh,
             c.precipitation_mm, c.pm2_5, c.us_aqi, c.heat_index_category,
             r.rain_next_6h_mm, r.rain_level
      FROM gold_latest_conditions c
      LEFT JOIN gold_rain_alert r ON r.location_id = c.location_id
      ORDER BY c.location`;
    const locations = rows.map((r) => ({ ...r, rain_next_6h_mm: num(r.rain_next_6h_mm) }));
    return NextResponse.json(
      { locations },
      { headers: { "Cache-Control": "s-maxage=300, stale-while-revalidate=600" } },
    );
  } catch (err) {
    console.error("GET /api/conditions failed", err);
    return NextResponse.json({ error: "Could not load conditions" }, { status: 500 });
  }
}
