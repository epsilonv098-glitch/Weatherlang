import { NextResponse } from "next/server";
import { getSql, num } from "@/lib/db";

export const dynamic = "force-dynamic";

/** Everything the place page needs: live row, 7-day history, and rankings vs other places. */
export async function GET(_req: Request, { params }: { params: Promise<{ name: string }> }) {
  const raw = (await params).name;
  let name = raw;
  try {
    name = decodeURIComponent(raw);
  } catch {}

  try {
    const sql = getSql();
    const [latest, hourly, daily, ranks] = await Promise.all([
      sql`SELECT c.location, c.area_type, c.observed_at, c.temperature_c, c.apparent_temp_c,
                 c.humidity_pct, c.wind_speed_kmh, c.pm2_5, c.us_aqi, c.heat_index_category,
                 r.rain_next_6h_mm, r.rain_level
          FROM gold_latest_conditions c
          LEFT JOIN gold_rain_alert r ON r.location_id = c.location_id
          WHERE lower(c.location) = lower(${name})`,
      sql`SELECT observed_at, temperature_c, us_aqi, humidity_pct
          FROM gold_observed_hourly
          WHERE lower(location) = lower(${name}) AND observed_at > now() - interval '7 days'
          ORDER BY observed_at`,
      sql`SELECT local_date::text AS local_date, total_rain_mm
          FROM gold_daily_avg
          WHERE lower(location) = lower(${name})
            AND local_date > (now() AT TIME ZONE 'Asia/Manila')::date - 7
          ORDER BY local_date`,
      sql`SELECT location, avg_aqi_24h, avg_apparent_temp_24h_c, total_rain_24h_mm,
                 aqi_rank, heat_rank, rain_rank
          FROM gold_rankings ORDER BY aqi_rank`,
    ]);

    if (latest.length === 0) {
      return NextResponse.json({ error: "Place not found" }, { status: 404 });
    }
    const p = latest[0];
    return NextResponse.json(
      {
        place: { ...p, rain_next_6h_mm: num(p.rain_next_6h_mm) },
        hourly: hourly.map((h) => ({
          t: new Date(h.observed_at).getTime(),
          temp: h.temperature_c,
          aqi: h.us_aqi,
          humidity: h.humidity_pct,
        })),
        daily: daily.map((d) => ({ date: d.local_date, rain: num(d.total_rain_mm) })),
        ranks: ranks.map((r) => ({
          location: r.location,
          aqi: num(r.avg_aqi_24h),
          heat: num(r.avg_apparent_temp_24h_c),
          rain: num(r.total_rain_24h_mm),
          aqiRank: num(r.aqi_rank),
          heatRank: num(r.heat_rank),
          rainRank: num(r.rain_rank),
        })),
      },
      { headers: { "Cache-Control": "s-maxage=300, stale-while-revalidate=600" } },
    );
  } catch (err) {
    console.error("GET /api/place failed", err);
    return NextResponse.json({ error: "Could not load this place" }, { status: 500 });
  }
}
