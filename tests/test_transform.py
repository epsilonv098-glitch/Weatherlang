"""Offline tests for pipeline.transform, using tiny hand-made API responses."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pipeline import extract, transform
from pipeline.config import Location
from pipeline.extract import LocationExtract

FETCHED = datetime(2026, 9, 29, 6, 0, tzinfo=timezone.utc)
CEBU = Location("Cebu City", "metro", 10.3157, 123.8854)
OSLOB = Location("Oslob", "tourist", 9.5222, 123.3814)


def body(hourly: dict[str, list[Any]], offset: int = 28800) -> dict[str, Any]:
    """Shape of an Open-Meteo response, trimmed to what transform reads."""
    return {"utc_offset_seconds": offset, "hourly": hourly}


WEATHER = body({
    "time": ["2026-09-29T08:00", "2026-09-29T09:00"],
    "temperature_2m": [29.5, 31.0],
    "apparent_temperature": [34.0, None],
    "relative_humidity_2m": [80, 75],
    "wind_speed_10m": [10.0, 12.0],
    "wind_gusts_10m": [20.0, 25.0],
    "precipitation": [0.0, 0.4],
    "weather_code": [3, 61],
})
AIR = body({
    "time": ["2026-09-29T08:00", "2026-09-29T09:00"],
    "pm2_5": [12.0, 14.5],
    "pm10": [20.0, 22.0],
    "us_aqi": [50, 55],
})
MARINE = body({
    "time": ["2026-09-29T08:00", "2026-09-29T09:00"],
    "wave_height": [0.6, None],
    "wave_period": [5.0, 5.5],
})


def make_extract(loc: Location, **sources: dict[str, Any]) -> LocationExtract:
    return LocationExtract(location=loc, fetched_at=FETCHED, sources=dict(sources))


def test_heat_category_boundaries() -> None:
    cases = [(None, None), (20.0, "Normal"), (32.9, "Normal"), (33.0, "Caution"),
             (41.9, "Caution"), (42.0, "Danger"), (55.0, "Danger")]
    for apparent, expected in cases:
        assert transform.heat_category(apparent) == expected, apparent


def test_local_time_is_converted_to_utc() -> None:
    utc = transform.to_utc("2026-09-29T08:00", 28800)
    assert utc == datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc)
    assert utc.tzinfo == timezone.utc


def test_midnight_rolls_back_a_day() -> None:
    utc = transform.to_utc("2026-09-29T03:00", 28800)
    assert utc == datetime(2026, 9, 28, 19, 0, tzinfo=timezone.utc)


def test_unparseable_time_becomes_none() -> None:
    assert transform.to_utc("not-a-time", 28800) is None
    assert transform.to_utc(None, 28800) is None


def test_weather_and_air_are_merged_per_hour() -> None:
    obs, marine = transform.flatten_extract(make_extract(CEBU, weather=WEATHER, air_quality=AIR))
    assert marine == []
    assert len(obs) == 2
    first = obs[0]
    assert first["location"] == "Cebu City"
    assert first["observed_at"] == datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc)
    assert first["temperature_c"] == 29.5 and first["us_aqi"] == 50
    assert obs[1]["apparent_temp_c"] is None  # nulls pass through untouched


def test_marine_rows_are_separate() -> None:
    obs, marine = transform.flatten_extract(
        make_extract(OSLOB, weather=WEATHER, air_quality=AIR, marine=MARINE)
    )
    assert len(obs) == 2 and len(marine) == 2
    assert marine[0]["wave_height_m"] == 0.6
    assert marine[1]["wave_height_m"] is None
    assert "wave_height_m" not in obs[0]


def test_failed_source_leaves_columns_absent() -> None:
    obs, _ = transform.flatten_extract(make_extract(CEBU, air_quality=AIR))
    assert len(obs) == 2
    assert obs[0]["us_aqi"] == 50 and "temperature_c" not in obs[0]


def test_missing_offset_defaults_to_manila() -> None:
    no_offset = {"hourly": WEATHER["hourly"]}
    obs, _ = transform.flatten_extract(make_extract(CEBU, weather=no_offset))
    assert obs[0]["observed_at"] == datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc)


def test_short_series_does_not_crash() -> None:
    ragged = body({"time": ["2026-09-29T08:00", "2026-09-29T09:00"], "temperature_2m": [29.5]})
    obs, _ = transform.flatten_extract(make_extract(CEBU, weather=ragged))
    assert obs[1]["temperature_c"] is None


def test_read_raw_files_roundtrip_and_ordering(tmp_path) -> None:
    older = LocationExtract(CEBU, FETCHED, {"weather": WEATHER})
    newer = LocationExtract(OSLOB, datetime(2026, 9, 29, 7, 0, tzinfo=timezone.utc), {"weather": WEATHER})
    extract.save_raw(newer, tmp_path)
    extract.save_raw(older, tmp_path)
    (tmp_path / "2026-09-29" / "9999_broken.json").write_text("{not json", encoding="utf-8")

    loaded = transform.read_raw_files(tmp_path)
    assert [e.location.name for e in loaded] == ["Cebu City", "Oslob"]  # oldest first
    assert loaded[0].sources["weather"] == WEATHER
    assert loaded[0].location == CEBU
