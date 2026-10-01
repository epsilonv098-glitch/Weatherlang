-- Cebu Pulse: gold layer, plain views over the silver tables. Safe to re-run:
-- everything is dropped and rebuilt, so edit freely and re-apply.
--
-- Conventions
--   * "History" means observed_at <= now(). Silver also holds forecast hours
--     (for rain_alert); every history view filters them out.
--   * Day and hour buckets use Asia/Manila local time, not UTC.

DROP VIEW IF EXISTS
    gold_beach_score, gold_rain_alert, gold_aqi_by_hour, gold_rankings,
    gold_rolling_7d, gold_daily_avg, gold_latest_conditions, gold_observed_hourly
CASCADE;

-- Base: hourly history with location names and a Manila local timestamp.
CREATE VIEW gold_observed_hourly AS
SELECT o.location_id,
       l.name AS location,
       l.area_type,
       o.observed_at,
       o.observed_at AT TIME ZONE 'Asia/Manila' AS local_time,
       o.temperature_c, o.apparent_temp_c, o.humidity_pct,
       o.wind_speed_kmh, o.wind_gust_kmh, o.precipitation_mm, o.weather_code,
       o.pm2_5, o.pm10, o.us_aqi, o.heat_index_category
FROM observations_silver o
JOIN locations l ON l.id = o.location_id
WHERE o.observed_at <= now();

-- Current conditions: the newest observed hour per location (map + place page).
CREATE VIEW gold_latest_conditions AS
SELECT DISTINCT ON (h.location_id)
       h.location_id, h.location, h.area_type, l.lat, l.lon,
       h.observed_at, h.local_time,
       h.temperature_c, h.apparent_temp_c, h.humidity_pct,
       h.wind_speed_kmh, h.wind_gust_kmh, h.precipitation_mm, h.weather_code,
       h.pm2_5, h.pm10, h.us_aqi, h.heat_index_category
FROM gold_observed_hourly h
JOIN locations l ON l.id = h.location_id
ORDER BY h.location_id, h.observed_at DESC;

-- 1. Daily averages per location (Manila calendar days; today is a partial day).
CREATE VIEW gold_daily_avg AS
SELECT location_id, location, area_type,
       local_time::date AS local_date,
       ROUND(AVG(temperature_c)::numeric, 1)      AS avg_temp_c,
       ROUND(MIN(temperature_c)::numeric, 1)      AS min_temp_c,
       ROUND(MAX(temperature_c)::numeric, 1)      AS max_temp_c,
       ROUND(AVG(apparent_temp_c)::numeric, 1)    AS avg_apparent_temp_c,
       ROUND(MAX(apparent_temp_c)::numeric, 1)    AS max_apparent_temp_c,
       ROUND(AVG(humidity_pct)::numeric, 0)       AS avg_humidity_pct,
       ROUND(SUM(precipitation_mm)::numeric, 1)   AS total_rain_mm,
       ROUND(AVG(us_aqi), 0)                      AS avg_aqi,
       ROUND(AVG(pm2_5)::numeric, 1)              AS avg_pm2_5,
       COUNT(*)                                   AS hours_count
FROM gold_observed_hourly
GROUP BY location_id, location, area_type, local_time::date;

-- 2. Rolling 7-day trends: each day compared with the 7 days ending on it.
--    days_in_window is below 7 until a location has a week of history.
CREATE VIEW gold_rolling_7d AS
SELECT location_id, location, area_type, local_date,
       avg_temp_c, avg_aqi, total_rain_mm,
       ROUND(AVG(avg_temp_c) OVER w, 1)              AS rolling_7d_avg_temp_c,
       ROUND(AVG(avg_aqi) OVER w, 0)                 AS rolling_7d_avg_aqi,
       ROUND(SUM(total_rain_mm) OVER w, 1)           AS rolling_7d_rain_mm,
       ROUND(avg_temp_c - AVG(avg_temp_c) OVER w, 1) AS temp_vs_7d_avg_c,
       COUNT(*) OVER w                               AS days_in_window
FROM gold_daily_avg
WINDOW w AS (PARTITION BY location_id ORDER BY local_date
             RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW);

-- 3. Rankings over the last 24 hours.
--    aqi_rank 1 = cleanest air, heat_rank 1 = hottest, rain_rank 1 = wettest.
CREATE VIEW gold_rankings AS
WITH last_24h AS (
    SELECT location_id, location, area_type,
           AVG(us_aqi)           AS avg_aqi,
           AVG(apparent_temp_c)  AS avg_apparent_temp_c,
           SUM(precipitation_mm) AS total_rain_mm
    FROM gold_observed_hourly
    WHERE observed_at > now() - INTERVAL '24 hours'
    GROUP BY location_id, location, area_type
)
SELECT location_id, location, area_type,
       ROUND(avg_aqi, 0)                      AS avg_aqi_24h,
       ROUND(avg_apparent_temp_c::numeric, 1) AS avg_apparent_temp_24h_c,
       ROUND(total_rain_mm::numeric, 1)       AS total_rain_24h_mm,
       RANK() OVER (ORDER BY avg_aqi ASC NULLS LAST)              AS aqi_rank,
       RANK() OVER (ORDER BY avg_apparent_temp_c DESC NULLS LAST) AS heat_rank,
       RANK() OVER (ORDER BY total_rain_mm DESC NULLS LAST)       AS rain_rank
FROM last_24h;

-- 4. AQI by Manila hour of day, metro vs everywhere else.
--    Rush hours are 7-9 AM and 5-7 PM (hours 7, 8, 9, 17, 18, 19).
CREATE VIEW gold_aqi_by_hour AS
SELECT EXTRACT(HOUR FROM local_time)::int AS hour_of_day,
       CASE WHEN area_type = 'metro' THEN 'metro' ELSE 'other' END AS area_group,
       EXTRACT(HOUR FROM local_time)::int IN (7, 8, 9, 17, 18, 19) AS is_rush_hour,
       ROUND(AVG(us_aqi), 1)           AS avg_aqi,
       ROUND(AVG(pm2_5)::numeric, 1)   AS avg_pm2_5,
       COUNT(us_aqi)                   AS sample_count
FROM gold_observed_hourly
WHERE us_aqi IS NOT NULL
GROUP BY 1, 2, 3;

-- 5. Rain alert: forecast rain over the next 6 hours per location.
--    rain_level thresholds (6-hour total): <1 none, <5 light, <15 moderate, else heavy.
CREATE VIEW gold_rain_alert AS
SELECT l.id   AS location_id,
       l.name AS location,
       l.area_type,
       ROUND(SUM(o.precipitation_mm)::numeric, 1) AS rain_next_6h_mm,
       ROUND(MAX(o.precipitation_mm)::numeric, 1) AS peak_hour_mm,
       COUNT(o.precipitation_mm)                  AS hours_covered,
       CASE
           WHEN COUNT(o.precipitation_mm) = 0      THEN 'unknown'
           WHEN SUM(o.precipitation_mm) >= 15      THEN 'heavy'
           WHEN SUM(o.precipitation_mm) >= 5       THEN 'moderate'
           WHEN SUM(o.precipitation_mm) >= 1       THEN 'light'
           ELSE 'none'
       END AS rain_level
FROM locations l
LEFT JOIN observations_silver o
       ON o.location_id = l.id
      AND o.observed_at > now()
      AND o.observed_at <= now() + INTERVAL '6 hours'
GROUP BY l.id, l.name, l.area_type;

-- 6. Beach score (0-100) for tourist spots. Weighted blend of three 0-100 parts:
--      waves 50%: 100 at <= 0.3 m, falling to 0 at >= 2.0 m
--      wind  30%: 100 at <= 10 km/h, falling to 0 at >= 40 km/h
--      rain  20%: 100 at 0 mm, falling to 0 at >= 10 mm expected in the next 6 h
--    Missing wave or wind data gives no score ("No data"); missing rain counts as 0 mm.
CREATE VIEW gold_beach_score AS
WITH latest_marine AS (
    SELECT DISTINCT ON (location_id)
           location_id, observed_at, wave_height_m, wave_period_s
    FROM marine_silver
    WHERE observed_at <= now() AND wave_height_m IS NOT NULL
    ORDER BY location_id, observed_at DESC
),
parts AS (
    SELECT l.id AS location_id, l.name AS location,
           m.observed_at AS marine_observed_at,
           m.wave_height_m, m.wave_period_s,
           c.wind_speed_kmh, c.wind_gust_kmh,
           COALESCE(r.rain_next_6h_mm, 0)::double precision AS rain_next_6h_mm,
           GREATEST(0, LEAST(100, 100 * (2.0 - m.wave_height_m) / 1.7))   AS wave_score,
           GREATEST(0, LEAST(100, 100 * (40.0 - c.wind_speed_kmh) / 30.0)) AS wind_score,
           GREATEST(0, LEAST(100, 100 * (10.0 - COALESCE(r.rain_next_6h_mm, 0)::double precision) / 10.0)) AS rain_score
    FROM locations l
    LEFT JOIN latest_marine m            ON m.location_id = l.id
    LEFT JOIN gold_latest_conditions c   ON c.location_id = l.id
    LEFT JOIN gold_rain_alert r          ON r.location_id = l.id
    WHERE l.area_type = 'tourist'
),
scored AS (
    SELECT *, 0.5 * wave_score + 0.3 * wind_score + 0.2 * rain_score AS raw_score
    FROM parts
)
SELECT location_id, location, marine_observed_at,
       wave_height_m, wave_period_s, wind_speed_kmh, wind_gust_kmh, rain_next_6h_mm,
       ROUND(raw_score::numeric)::int AS beach_score,
       CASE
           WHEN raw_score IS NULL                        THEN 'No data'
           WHEN wave_height_m >= 1.5 OR raw_score < 40   THEN 'Rough seas'
           WHEN raw_score >= 80                          THEN 'Good for swimming'
           WHEN raw_score >= 60                          THEN 'Fair, swim with care'
           ELSE 'Choppy, stay near shore'
       END AS verdict
FROM scored;
