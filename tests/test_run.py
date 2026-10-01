"""Offline tests for pipeline.run: run tracking on success and on every failure mode."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from fake_db import FakeConn, FakeRecord, make_batch
from pipeline import run

T0 = datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc)


def record(location: str = "Cebu City") -> FakeRecord:
    return FakeRecord(location=location, observed_at=T0, temperature_c=30.0, us_aqi=50)


def final_update(conn: FakeConn) -> tuple[str, ...]:
    """Params of the last UPDATE pipeline_runs: (status, ingested, rejected, error, run_id)."""
    return conn.starting("UPDATE pipeline_runs")[-1][1]


def patch_pipeline(monkeypatch: pytest.MonkeyPatch, batch: Any = None, extract_error: Exception | None = None,
                   silver_error: Exception | None = None) -> None:
    def fake_extraction() -> list[Any]:
        if extract_error:
            raise extract_error
        return []

    def fake_silver(_extracts: Any) -> Any:
        if silver_error:
            raise silver_error
        return batch

    monkeypatch.setattr(run.extract, "run_extraction", fake_extraction)
    monkeypatch.setattr(run.validate, "build_silver", fake_silver)


def test_successful_run_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_pipeline(monkeypatch, batch=make_batch([record(), record("Oslob")], rejected=3))
    conn = FakeConn()

    assert run.execute(conn) == 0
    status, ingested, rejected, error, _run_id = final_update(conn)
    assert (status, ingested, rejected, error) == ("success", 2, 3, None)
    assert conn.rollbacks == 0
    assert len(conn.starting("INSERT INTO observations_silver")) == 1


def test_failure_rolls_back_and_records_the_error(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_pipeline(monkeypatch, silver_error=ValueError("boom"))
    conn = FakeConn()

    assert run.execute(conn) == 1
    status, ingested, _rejected, error, _run_id = final_update(conn)
    assert status == "failed" and ingested == 0
    assert "ValueError" in error and "boom" in error
    assert conn.rollbacks == 1
    assert conn.starting("INSERT INTO observations_silver") == []


def test_extraction_crash_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_pipeline(monkeypatch, extract_error=RuntimeError("network down"))
    conn = FakeConn()

    assert run.execute(conn) == 1
    assert final_update(conn)[0] == "failed"


def test_nothing_valid_to_load_counts_as_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_pipeline(monkeypatch, batch=make_batch([], rejected=5))
    conn = FakeConn()

    assert run.execute(conn) == 1
    status, ingested, rejected, error, _run_id = final_update(conn)
    assert (status, ingested, rejected) == ("failed", 0, 5)
    assert "no valid rows" in error


def test_long_errors_are_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_pipeline(monkeypatch, silver_error=RuntimeError("x" * 5000))
    conn = FakeConn()

    run.execute(conn)
    assert len(final_update(conn)[3]) == run.MAX_ERROR_CHARS
