"""Offline tests for pipeline.quality_checks, using plain stand-in records (no pydantic, no DB)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from pipeline import quality_checks as qc
from pipeline.config import LOCATIONS

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
NAMES = [loc.name for loc in LOCATIONS]


def rec(location: str = "Cebu City", hours_ago: float = 0.5, **overrides: Any) -> SimpleNamespace:
    """A fully populated observation; override fields (e.g. us_aqi=None) to degrade it."""
    fields: dict[str, Any] = {name: 1.0 for name in qc.OBS_FIELDS}
    fields.update(location=location, observed_at=NOW - timedelta(hours=hours_ago))
    fields.update(overrides)
    return SimpleNamespace(**fields)


def batch(records: list[Any], marine: list[Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        observations=SimpleNamespace(records=records),
        marine=SimpleNamespace(records=marine or []),
    )


def healthy(n_locations: int = 12) -> list[SimpleNamespace]:
    return [rec(name) for name in NAMES[:n_locations]]


# --- freshness -------------------------------------------------------------

def test_fresh_data_passes() -> None:
    assert qc.check_freshness([rec(hours_ago=0.5)], NOW).passed


def test_three_hours_old_is_still_ok_but_more_fails() -> None:
    assert qc.check_freshness([rec(hours_ago=3.0)], NOW).passed
    result = qc.check_freshness([rec(hours_ago=3.1)], NOW)
    assert not result.passed and "3.1h" in result.detail


def test_future_forecast_rows_do_not_count_as_fresh() -> None:
    records = [rec(hours_ago=5), rec(hours_ago=-6)]  # one stale, one forecast
    assert not qc.check_freshness(records, NOW).passed


def test_freshness_fails_with_no_observed_rows() -> None:
    assert not qc.check_freshness([], NOW).passed
    assert not qc.check_freshness([rec(hours_ago=-2)], NOW).passed  # only forecast


# --- null rate -------------------------------------------------------------

def test_no_nulls_passes() -> None:
    assert qc.check_null_rate(healthy()).passed


def test_null_rate_boundary_is_inclusive_at_ten_percent() -> None:
    ten_rows = [rec(us_aqi=None) for _ in range(10)]  # 1 of 10 fields null = exactly 10%
    assert qc.check_null_rate(ten_rows).passed
    worse = [rec(us_aqi=None, pm10=None) if i == 0 else rec(us_aqi=None) for i in range(10)]
    result = qc.check_null_rate(worse)  # 11 of 100 values null
    assert not result.passed
    assert "us_aqi" in result.detail  # names the worst field


def test_null_rates_overall_and_per_field() -> None:
    records = [rec(us_aqi=None), rec()]
    overall, per_field = qc.null_rates(records, qc.OBS_FIELDS)
    assert per_field["us_aqi"] == 0.5 and per_field["temperature_c"] == 0.0
    assert overall == pytest.approx(1 / len(qc.OBS_FIELDS) * 0.5)


def test_empty_records_count_as_fully_null() -> None:
    overall, _ = qc.null_rates([], qc.OBS_FIELDS)
    assert overall == 1.0
    assert not qc.check_null_rate([]).passed


# --- coverage --------------------------------------------------------------

def test_all_twelve_locations_pass() -> None:
    assert qc.check_coverage(healthy(12)).passed


def test_ten_of_twelve_is_the_minimum() -> None:
    assert qc.check_coverage(healthy(10)).passed
    result = qc.check_coverage(healthy(9))
    assert not result.passed
    assert "9 of 12" in result.detail
    assert NAMES[9] in result.detail  # lists who is missing


def test_many_rows_for_one_location_is_not_coverage() -> None:
    records = [rec("Cebu City", hours_ago=h) for h in range(40)]
    assert not qc.check_coverage(records).passed


# --- enforce ---------------------------------------------------------------

def test_enforce_passes_a_healthy_batch() -> None:
    results = qc.enforce(batch(healthy()), NOW)
    assert [r.name for r in results] == ["freshness", "null_rate", "coverage"]
    assert all(r.passed for r in results)


def test_enforce_raises_and_lists_every_failure() -> None:
    stale_and_thin = [rec(name, hours_ago=6) for name in NAMES[:5]]
    with pytest.raises(qc.QualityCheckError) as excinfo:
        qc.enforce(batch(stale_and_thin), NOW)
    message = str(excinfo.value)
    assert "freshness" in message and "coverage" in message
    assert {f.name for f in excinfo.value.failures} == {"freshness", "coverage"}


def test_marine_nulls_warn_but_never_block() -> None:
    sea = [SimpleNamespace(wave_height_m=None, wave_period_s=None) for _ in range(5)]
    results = qc.enforce(batch(healthy(), marine=sea), NOW)
    assert all(r.passed for r in results)
