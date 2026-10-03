import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";

export const dynamic = "force-dynamic";
const MAX_PLACES = 3;

/** Hourly history (last 7 days) for up to 3 places: /api/compare?places=Cebu%20City,Oslob */
export async function GET(req: Request) {
  const raw = new URL(req.url).searchParams.get("places") ?? "";
  const names = [...new Set(raw.split(",").map((s) => s.trim()).filter(Boolean))].slice(0, MAX_PLACES);
  if (names.length === 0) {
    return NextResponse.json({ error: "Pick at least one place" }, { status: 400 });
  }

  try {
    const sql = getSql();
    const results = await Promise.all(
      names.map(
        (name) => sql`
          SELECT location, observed_at, temperature_c, us_aqi, humidity_pct, precipitation_mm
          FROM gold_observed_hourly
          WHERE lower(location) = lower(${name}) AND observed_at > now() - interval '7 days'
          ORDER BY observed_at`,
      ),
    );
    const series = names.map((name, i) => ({
      name: results[i][0]?.location ?? name,
      points: results[i].map((r) => ({
        t: new Date(r.observed_at).getTime(),
        temp: r.temperature_c,
        aqi: r.us_aqi,
        humidity: r.humidity_pct,
        rain: r.precipitation_mm,
      })),
    }));
    return NextResponse.json(
      { series },
      { headers: { "Cache-Control": "s-maxage=300, stale-while-revalidate=600" } },
    );
  } catch (err) {
    console.error("GET /api/compare failed", err);
    return NextResponse.json({ error: "Could not load comparison data" }, { status: 500 });
  }
}
