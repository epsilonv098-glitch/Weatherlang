# Design decisions

Each entry: what was decided, why, and the trade-off.

## ELT with bronze, silver and gold
**Decision:** save raw API JSON first (bronze), validate and store clean rows (silver), then build views for the site (gold).
**Why:** raw data is never lost, so a bug in cleaning can be fixed and replayed. Each layer has one job and is easy to test.
**Trade-off:** more moving parts than writing straight to a table.

## Idempotent upserts
**Decision:** every write is `INSERT ... ON CONFLICT (location_id, observed_at) DO UPDATE`.
**Why:** hourly runs overlap (each fetch holds yesterday, today and tomorrow), and a retry must not duplicate rows. Values update as forecast hours become past hours.
**Details:** `COALESCE` keeps a stored value when a new fetch has a null, so one failed source cannot erase good data. Locations are looked up first and only inserted when missing, because an `ON CONFLICT` insert burns an identity value on every run.

## GitHub Actions as the orchestrator
**Decision:** an hourly cron workflow (minute :07) runs the pipeline. No Airflow, no servers.
**Why:** free, version-controlled, secrets built in, and enough for one short job per hour.
**Trade-off:** scheduled runs can start late and have no retry UI. A concurrency group stops overlapping runs. Raw files are committed once a day, not hourly, to keep git history small.

## Neon Postgres
**Decision:** Neon, created through Vercel's Neon integration.
**Why:** free serverless Postgres, plain SQL for the gold layer, and an HTTP driver that works from Vercel functions.
**Trade-off:** compute scales to zero, so the first query after idle is slower.

## UTC storage, Manila display
**Decision:** all timestamps are `timestamptz` (UTC). The API is asked for `Asia/Manila`, converted to UTC on ingest, and shown in Manila time. Day and hour buckets in SQL use `AT TIME ZONE 'Asia/Manila'`.
**Why:** one unambiguous stored time. Manila has no daylight saving, so the fixed +8 fallback is safe.

## Quality gate before load
**Decision:** fail the run, and load nothing, if the newest data is over 3 hours old, over 10% of weather and air values are null, or fewer than 10 of 12 places returned data.
**Why:** a stale or thin batch is worse than keeping the last good data.
**Detail:** the marine null rate only logs a warning, because sea data is patchier.

## Validation rules
- An impossible value (temperature outside 10 to 50 C, humidity outside 0 to 100) rejects the whole row, and the reason is logged.
- A single null field is kept, so the null-rate check can see it. A row with every measurement null is rejected.
- Duplicates on (location, time) keep the newest copy and count as rejected.

## Heat categories
**Decision:** below 33 C Normal, 33 to 41 C Caution, 42 C and up Danger, using apparent temperature.
**Why:** this folds PAGASA's four heat index classes into three labels. PAGASA's lowest class (27 to 32 C) is ordinary weather in Cebu, so it counts as Normal.
**Caveat:** Open-Meteo's apparent temperature is a stand-in, not PAGASA's official heat index.

## Gold models
- Gold views only use history (`observed_at <= now()`). Forecast hours feed only the rain alert.
- Rain levels use the 6-hour total: under 1 mm none, under 5 light, under 15 moderate, otherwise heavy.
- Beach score is 50% waves, 30% wind and 20% expected rain. It is a guide, not a safety forecast.
- Sea data is fetched for all 12 places, so every place gets a beach score. Some places may have no wave data.
- Rush hours are 7 to 9 AM and 5 to 7 PM.

## Web app
- Postgres `numeric` values reach JavaScript as strings, so API routes convert them.
- Place names are matched case-insensitively, so there is no slug column.
- The site shows modeled data and says so in the footer.
