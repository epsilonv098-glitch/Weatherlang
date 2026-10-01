"""Phase 3 (load): idempotent upserts into Neon Postgres, plus pipeline_runs tracking.

Apply the schema and gold views once with:  python -m pipeline.load init
The connection string comes only from the DATABASE_URL environment variable.
"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Sequence

import psycopg

from pipeline import config
from pipeline.config import LOCATIONS, Location

if TYPE_CHECKING:  # type hints only; keeps this module importable without pydantic
    from pipeline.validate import SilverBatch

log = logging.getLogger(__name__)

SQL_DIR = config.PROJECT_ROOT / "sql"

# Column order must match sql/schema.sql (a test checks this).
OBS_COLUMNS = (
    "temperature_c", "apparent_temp_c", "humidity_pct", "wind_speed_kmh",
    "wind_gust_kmh", "precipitation_mm", "weather_code", "pm2_5", "pm10",
    "us_aqi", "heat_index_category",
)
MARINE_COLUMNS = ("wave_height_m", "wave_period_s")


def get_database_url() -> str:
    """DATABASE_URL from the environment; never hardcoded, never logged."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Export your Neon connection string first.")
    return url


def connect() -> psycopg.Connection:
    """Open a connection (psycopg default: changes need an explicit commit)."""
    return psycopg.connect(get_database_url(), connect_timeout=15)


def apply_sql_files(conn: psycopg.Connection, paths: Iterable[Path]) -> None:
    """Run .sql files in order. The files are written to be safe to re-run."""
    for path in paths:
        log.info("Applying %s", path.name)
        conn.execute(path.read_text(encoding="utf-8"))
        conn.commit()


def sync_locations(
    conn: psycopg.Connection, locations: Sequence[Location] = LOCATIONS
) -> dict[str, int]:
    """Make the locations table match config and return {name: id}.

    Existing rows are updated and only missing ones inserted. A blanket
    INSERT ... ON CONFLICT would burn an identity value on every run.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT name, id FROM locations")
        ids: dict[str, int] = dict(cur.fetchall())
        for loc in locations:
            if loc.name in ids:
                cur.execute(
                    "UPDATE locations SET area_type = %s, lat = %s, lon = %s WHERE id = %s",
                    (loc.area_type, loc.lat, loc.lon, ids[loc.name]),
                )
            else:
                cur.execute(
                    "INSERT INTO locations (name, area_type, lat, lon) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    (loc.name, loc.area_type, loc.lat, loc.lon),
                )
                ids[loc.name] = cur.fetchone()[0]
    return ids


def _upsert_sql(table: str, columns: Sequence[str]) -> str:
    """Build an idempotent upsert. Table and columns are code constants, never user input.

    COALESCE keeps the stored value when a new fetch has a null (for example one
    source failed this run), so a partial failure cannot erase good data.
    """
    all_cols = ("location_id", "observed_at", *columns)
    names = ", ".join(all_cols)
    placeholders = ", ".join(f"%({c})s" for c in all_cols)
    updates = ", ".join(f"{c} = COALESCE(EXCLUDED.{c}, {table}.{c})" for c in columns)
    return (
        f"INSERT INTO {table} ({names}) VALUES ({placeholders}) "
        f"ON CONFLICT (location_id, observed_at) DO UPDATE SET {updates}, updated_at = now()"
    )


def build_params(
    records: Iterable[Any], location_ids: dict[str, int], columns: Sequence[str]
) -> list[dict[str, Any]]:
    """Silver records -> parameter dicts for the upsert. Unknown locations are skipped."""
    params: list[dict[str, Any]] = []
    skipped = 0
    for record in records:
        data = record.model_dump()
        location_id = location_ids.get(data["location"])
        if location_id is None:
            skipped += 1
            continue
        row = {"location_id": location_id, "observed_at": data["observed_at"]}
        row.update({col: data.get(col) for col in columns})
        params.append(row)
    if skipped:
        log.warning("Skipped %d records for locations not in the database", skipped)
    return params


def _upsert(
    conn: psycopg.Connection,
    table: str,
    columns: Sequence[str],
    records: Iterable[Any],
    location_ids: dict[str, int],
) -> int:
    params = build_params(records, location_ids, columns)
    if not params:
        return 0
    with conn.cursor() as cur:
        cur.executemany(_upsert_sql(table, columns), params)
    return len(params)


def load_batch(
    conn: psycopg.Connection, batch: "SilverBatch", locations: Sequence[Location] = LOCATIONS
) -> tuple[int, int]:
    """Upsert a whole batch in ONE transaction: all of it lands or none of it.

    Returns (observation_rows, marine_rows) written.
    """
    ids = sync_locations(conn, locations)
    n_obs = _upsert(conn, "observations_silver", OBS_COLUMNS, batch.observations.records, ids)
    n_marine = _upsert(conn, "marine_silver", MARINE_COLUMNS, batch.marine.records, ids)
    conn.commit()
    log.info("Loaded %d observation rows and %d marine rows", n_obs, n_marine)
    return n_obs, n_marine


def start_run(conn: psycopg.Connection) -> int:
    """Insert a 'running' pipeline_runs row and commit it right away."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO pipeline_runs (status) VALUES ('running') RETURNING id")
        run_id = int(cur.fetchone()[0])
    conn.commit()
    return run_id


def finish_run(
    conn: psycopg.Connection,
    run_id: int,
    status: str,
    rows_ingested: int,
    rows_rejected: int,
    error: str | None = None,
) -> None:
    """Close out a pipeline_runs row with its final status and counts."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE pipeline_runs SET finished_at = now(), status = %s, "
            "rows_ingested = %s, rows_rejected = %s, error = %s WHERE id = %s",
            (status, rows_ingested, rows_rejected, error, run_id),
        )
    conn.commit()


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: `init` applies sql/schema.sql then sql/gold_models.sql."""
    parser = argparse.ArgumentParser(description="Cebu Pulse database helpers")
    parser.add_argument("command", choices=["init"], help="apply schema and gold views")
    parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        with connect() as conn:
            apply_sql_files(conn, [SQL_DIR / "schema.sql", SQL_DIR / "gold_models.sql"])
    except (RuntimeError, psycopg.Error) as exc:
        log.error("init failed: %s", exc)
        return 2
    log.info("Schema and gold views are in place")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
