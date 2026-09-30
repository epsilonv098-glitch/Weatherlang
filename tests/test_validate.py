"""Offline tests for pipeline.validate: bounds, nulls, dedupe and reject accounting."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pipeline.validate import (
    MarineRecord,
    ObservationRecord,
    ValidationResult,
    validate_rows,
)

T0 = datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc)


def obs_row(**overrides: Any) -> dict[str, Any]:
    """A plausible valid observation row; override fields to break it."""
    row: dict[str, Any] = {
        "location": "Cebu City",
        "observed_at": T0,
        "temperature_c": 30.0,
        "apparent_temp_c": 35.0,
        "humidity_pct": 80,
        "wind_speed_kmh": 10.0,
        "wind_gust_kmh": 20.0,
        "precipitation_mm": 0.0,
        "weather_code": 3,
        "pm2_5": 12.0,
        "pm10": 20.0,
        "us_aqi": 50,
    }
    row.update(overrides)
    return row


def run(rows: list[dict[str, Any]]) -> ValidationResult[ObservationRecord]:
    return validate_rows(rows, ObservationRecord, "test")


def test_valid_row_passes_and_gets_heat_category() -> None:
    result = run([obs_row()])
    assert result.rejected_count == 0
    assert len(result.records) == 1
    assert result.records[0].heat_index_category == "Caution"  # 35 C feels-like


def test_heat_category_in_model_dump() -> None:
    dumped = run([obs_row(apparent_temp_c=43.0)]).records[0].model_dump()
    assert dumped["heat_index_category"] == "Danger"


def test_temperature_out_of_range_is_rejected_with_reason() -> None:
    result = run([obs_row(temperature_c=50.1), obs_row(temperature_c=9.9, observed_at=T0 + timedelta(hours=1))])
    assert result.records == []
    assert result.rejected["temperature_c:above_max"] == 1
    assert result.rejected["temperature_c:below_min"] == 1


def test_temperature_boundaries_are_valid() -> None:
    rows = [obs_row(temperature_c=10.0), obs_row(temperature_c=50.0, observed_at=T0 + timedelta(hours=1))]
    assert len(run(rows).records) == 2


def test_humidity_outside_0_100_is_rejected() -> None:
    rows = [obs_row(humidity_pct=101), obs_row(humidity_pct=-1, observed_at=T0 + timedelta(hours=1))]
    result = run(rows)
    assert result.records == []
    assert result.rejected["humidity_pct:above_max"] == 1
    assert result.rejected["humidity_pct:below_min"] == 1


def test_single_null_field_is_allowed() -> None:
    result = run([obs_row(pm2_5=None, us_aqi=None, apparent_temp_c=None)])
    assert len(result.records) == 1
    assert result.records[0].heat_index_category is None


def test_row_with_all_measurements_null_is_rejected() -> None:
    blank = {"location": "Cebu City", "observed_at": T0}
    result = run([blank])
    assert result.records == []
    assert result.rejected["row:all_null"] == 1


def test_missing_or_naive_timestamp_is_rejected() -> None:
    rows = [
        obs_row(observed_at=None),
        obs_row(observed_at=datetime(2026, 9, 29, 8, 0)),  # naive: no timezone
    ]
    result = run(rows)
    assert result.records == []
    assert result.rejected_count == 2


def test_non_numeric_value_is_rejected() -> None:
    result = run([obs_row(temperature_c="hot")])
    assert result.records == []
    assert result.rejected_count == 1


def test_aqi_float_is_rounded() -> None:
    assert run([obs_row(us_aqi=54.6)]).records[0].us_aqi == 55


def test_duplicates_keep_the_latest_and_are_counted() -> None:
    older = obs_row(temperature_c=28.0)
    newer = obs_row(temperature_c=31.0)  # same location + timestamp
    result = run([older, newer])
    assert len(result.records) == 1
    assert result.records[0].temperature_c == 31.0
    assert result.rejected["duplicate"] == 1


def test_same_time_different_location_is_not_a_duplicate() -> None:
    result = run([obs_row(), obs_row(location="Oslob")])
    assert len(result.records) == 2
    assert result.rejected_count == 0


def test_mixed_batch_totals_add_up() -> None:
    rows = [
        obs_row(),                                                            # valid
        obs_row(observed_at=T0 + timedelta(hours=1), temperature_c=60),       # bad temp
        obs_row(observed_at=T0 + timedelta(hours=2), humidity_pct=150),       # bad humidity
        obs_row(),                                                            # duplicate of first
    ]
    result = run(rows)
    assert result.total == 4
    assert len(result.records) == 1
    assert result.rejected_count == 3
    assert len(result.records) + result.rejected_count == result.total


def test_output_is_sorted_and_utc() -> None:
    later = obs_row(observed_at=T0 + timedelta(hours=5))
    result = run([later, obs_row()])
    assert [r.observed_at for r in result.records] == [T0, T0 + timedelta(hours=5)]
    assert result.records[0].observed_at.utcoffset() == timedelta(0)


def test_marine_record_rules() -> None:
    rows = [
        {"location": "Oslob", "observed_at": T0, "wave_height_m": 0.8, "wave_period_s": 6.0},
        {"location": "Oslob", "observed_at": T0 + timedelta(hours=1), "wave_height_m": -0.5, "wave_period_s": 6.0},
        {"location": "Oslob", "observed_at": T0 + timedelta(hours=2), "wave_height_m": None, "wave_period_s": None},
        {"location": "Oslob", "observed_at": T0 + timedelta(hours=3), "wave_height_m": None, "wave_period_s": 5.0},
    ]
    result = validate_rows(rows, MarineRecord, "marine")
    assert len(result.records) == 2  # the negative and the all-null rows are gone
    assert result.rejected["wave_height_m:below_min"] == 1
    assert result.rejected["row:all_null"] == 1
