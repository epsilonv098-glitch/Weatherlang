# Architecture

## Flow
1. **Extract** (`pipeline/extract.py`): three Open-Meteo calls per place (weather, air quality, sea), with timeouts and retry with backoff. A failed source is recorded, not fatal. Raw JSON is saved to `data/raw/YYYY-MM-DD/HHmm_place.json` (UTC).
2. **Transform** (`pipeline/transform.py`): unpivots hourly arrays into rows, merges weather and air by timestamp, converts local time to UTC, derives the heat category.
3. **Validate** (`pipeline/validate.py`): Pydantic models, bounds, null rules, dedupe, and a count of rejected rows by reason.
4. **Quality gate** (`pipeline/quality_checks.py`): freshness, null rate and coverage checks. Any failure stops the run before loading.
5. **Load** (`pipeline/load.py`): one transaction of upserts into Neon. `pipeline_runs` records every run.
6. **Gold** (`sql/gold_models.sql`): views over the silver tables.
7. **Serve** (`web/`): Next.js API routes query the gold views and the pages draw them.

## Tables
- `locations`: 12 places with area type and coordinates.
- `observations_silver`: one row per place and hour (weather and air). Primary key `(location_id, observed_at)`.
- `marine_silver`: one row per place and hour (waves).
- `pipeline_runs`: start, end, status, rows ingested and rejected, error.

## Gold views
`gold_observed_hourly`, `gold_latest_conditions`, `gold_daily_avg`, `gold_rolling_7d`, `gold_rankings`, `gold_aqi_by_hour`, `gold_rain_alert`, `gold_beach_score`.

## Run lifecycle
A run is inserted as `running`, then ends as `success` or `failed` with the error text. A failed run loads nothing, so the site keeps the last good data.

## Failure modes
- **One source down:** the place keeps its other data.
- **Many places missing, stale data, or too many nulls:** the run fails.
- **Database unreachable:** exit code 2, no run row.
- **Late or skipped cron:** the next run backfills, because each fetch covers yesterday through tomorrow.
