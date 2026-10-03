"""Offline tests for pipeline.extract. No network: HTTP is replaced by a scripted fake."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest
import requests

from pipeline import config, extract
from pipeline.config import LOCATIONS, Location

NOW = datetime(2026, 9, 29, 6, 5, tzinfo=timezone.utc)
METRO = Location("Cebu City", "metro", 10.3157, 123.8854)
BEACH = Location("Oslob", "tourist", 9.5222, 123.3814)
GOOD_BODY = {"hourly": {"time": ["2026-09-29T00:00"], "temperature_2m": [28.1]}}


class FakeResponse:
    """Just enough of requests.Response for fetch_json."""

    def __init__(self, status: int = 200, body: Any = None) -> None:
        self.status_code = status
        self._body = GOOD_BODY if body is None else body

    def json(self) -> Any:
        return self._body


class FakeSession:
    """Plays back a scripted list of responses/exceptions; then always succeeds."""

    def __init__(self, script: list[Any] | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any], timeout: float) -> FakeResponse:
        self.calls.append({"url": url, "params": params})
        item = self.script.pop(0) if self.script else FakeResponse()
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip real waiting so retry tests run instantly."""
    monkeypatch.setattr(extract.time, "sleep", lambda _seconds: None)


def test_retries_then_succeeds() -> None:
    session = FakeSession([FakeResponse(503), requests.ConnectionError("boom")])
    assert extract.fetch_json(session, "http://x", {}) == GOOD_BODY
    assert len(session.calls) == 3


def test_gives_up_after_max_retries() -> None:
    session = FakeSession([FakeResponse(500)] * 10)
    with pytest.raises(extract.ExtractError, match="gave up"):
        extract.fetch_json(session, "http://x", {})
    assert len(session.calls) == config.MAX_RETRIES


def test_client_error_is_not_retried() -> None:
    session = FakeSession([FakeResponse(400, {"error": True, "reason": "bad param"})])
    with pytest.raises(extract.ExtractError, match="bad param"):
        extract.fetch_json(session, "http://x", {})
    assert len(session.calls) == 1


def test_body_without_hourly_is_rejected() -> None:
    session = FakeSession([FakeResponse(200, {"latitude": 10.0})])
    with pytest.raises(extract.ExtractError, match="hourly"):
        extract.fetch_json(session, "http://x", {})


def test_marine_is_fetched_for_every_location() -> None:
    metro = extract.extract_location(FakeSession(), METRO, NOW)
    beach = extract.extract_location(FakeSession(), BEACH, NOW)
    assert set(metro.sources) == {"weather", "air_quality", "marine"}
    assert set(beach.sources) == {"weather", "air_quality", "marine"}
    assert metro.ok and beach.ok


def test_request_asks_for_manila_timezone() -> None:
    session = FakeSession()
    extract.extract_location(session, METRO, NOW)
    assert all(c["params"]["timezone"] == "Asia/Manila" for c in session.calls)


def test_partial_failure_is_recorded_not_raised() -> None:
    session = FakeSession([FakeResponse(200), FakeResponse(400, {"reason": "nope"})])
    result = extract.extract_location(session, METRO, NOW)
    assert "weather" in result.sources
    assert "nope" in result.errors["air_quality"]
    assert result.has_data and not result.ok


def test_save_raw_path_and_content(tmp_path) -> None:
    result = extract.extract_location(FakeSession(), METRO, NOW)
    path = extract.save_raw(result, tmp_path)
    assert path == tmp_path / "2026-09-29" / "0605_cebu_city.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["location"]["name"] == "Cebu City"
    assert set(doc["sources"]) == {"weather", "air_quality", "marine"}


def test_save_raw_skips_location_with_no_data(tmp_path) -> None:
    empty = extract.LocationExtract(location=METRO, fetched_at=NOW)
    assert extract.save_raw(empty, tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_run_extraction_writes_one_file_per_location(tmp_path) -> None:
    results = extract.run_extraction(raw_dir=tmp_path, session=FakeSession(), now=NOW)
    assert len(results) == 12
    assert len(list((tmp_path / "2026-09-29").glob("0605_*.json"))) == 12


def test_location_config_shape() -> None:
    by_type = [loc.area_type for loc in LOCATIONS]
    assert len(LOCATIONS) == 12
    assert (by_type.count("metro"), by_type.count("mainland"), by_type.count("tourist")) == (4, 4, 4)
