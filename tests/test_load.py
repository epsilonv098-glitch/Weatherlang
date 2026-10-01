"""Offline tests for pipeline.load, using a fake connection (no database needed)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import pytest

from fake_db import FakeConn, FakeRecord, make_batch
from pipeline import config, load

T0 = datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc)


def obs(location: str = "Cebu City", **overrides: Any) -> FakeRecord:
    fields: dict[str, Any] = {
        "location": location, "observed_at": T0, "temperature_c": 30.0,
        "apparent_temp_c": 35.0, "humidity_pct": 80.0, "wind_speed_kmh": 10.0,
        "wind_gust_kmh": 20.0, "precipitation_mm": 0.0, "weather_code": 3,
        "pm2_5": 12.0, "pm10": 20.0, "us_aqi": 50, "heat_index_category": "Caution",
    }
    fields.update(overrides)
    return FakeRecord(**fields)


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        load.get_database_url()
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    assert load.get_database_url() == "postgresql://example"


def test_upsert_sql_is_idempotent_and_null_safe() -> None:
    sql = load._upsert_sql("observations_silver", load.OBS_COLUMNS)
    assert "INSERT INTO observations_silver" in sql
    assert "ON CONFLICT (location_id, observed_at) DO UPDATE SET" in sql
    assert "us_aqi = COALESCE(EXCLUDED.us_aqi, observations_silver.us_aqi)" in sql
    assert "%(temperature_c)s" in sql and "%(location_id)s" in sql


def test_columns_match_schema_file() -> None:
    schema = (config.PROJECT_ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
    for table, columns in (("observations_silver", load.OBS_COLUMNS), ("marine_silver", load.MARINE_COLUMNS)):
        block = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", schema, re.S)
        assert block, f"{table} not found in schema.sql"
        for column in columns:
            assert re.search(rf"\b{column}\b", block.group(1)), f"{table}.{column} missing from schema"


def test_sync_locations_inserts_once_then_only_updates() -> None:
    first = FakeConn()
    ids = load.sync_locations(first)
    assert len(ids) == 12
    assert len(first.starting("INSERT INTO locations")) == 12

    existing = {name: i for i, name in enumerate(ids, start=100)}
    second = FakeConn(existing_locations=existing)
    assert load.sync_locations(second) == existing
    assert second.starting("INSERT INTO locations") == []
    assert len(second.starting("UPDATE locations")) == 12


def test_params_map_location_ids_and_skip_unknown() -> None:
    params = load.build_params([obs("Cebu City"), obs("Atlantis")], {"Cebu City": 7}, load.OBS_COLUMNS)
    assert len(params) == 1
    assert params[0]["location_id"] == 7
    assert set(params[0]) == {"location_id", "observed_at", *load.OBS_COLUMNS}
    assert params[0]["heat_index_category"] == "Caution"


def test_load_batch_upserts_both_tables_in_one_commit() -> None:
    conn = FakeConn()
    marine = FakeRecord(location="Oslob", observed_at=T0, wave_height_m=0.6, wave_period_s=5.0)
    batch = make_batch([obs("Cebu City"), obs("Oslob")], [marine])

    assert load.load_batch(conn, batch) == (2, 1)
    assert conn.commits == 1
    assert len(conn.starting("INSERT INTO observations_silver")) == 1
    assert len(conn.starting("INSERT INTO marine_silver")) == 1
    assert len(conn.starting("INSERT INTO observations_silver")[0][1]) == 2  # two param rows


def test_empty_batch_writes_no_upserts() -> None:
    conn = FakeConn()
    assert load.load_batch(conn, make_batch([])) == (0, 0)
    assert conn.starting("INSERT INTO observations_silver") == []


def test_start_and_finish_run_record_the_outcome() -> None:
    conn = FakeConn()
    run_id = load.start_run(conn)
    assert isinstance(run_id, int) and conn.commits == 1

    load.finish_run(conn, run_id, "failed", 0, 4, "boom")
    (_, params), = conn.starting("UPDATE pipeline_runs")
    assert params == ("failed", 0, 4, "boom", run_id)
    assert conn.commits == 2
