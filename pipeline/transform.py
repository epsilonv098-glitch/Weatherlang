"""Phase 2 (silver, step 1): reshape raw Open-Meteo JSON into flat, UTC-stamped rows.

This module only reshapes and derives; it never rejects anything. Rejecting
bad rows is validate.py's job.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Sequence

from pipeline.config import Location
from pipeline.extract import LocationExtract

log = logging.getLogger(__name__)

HeatCategory = Literal["Normal", "Caution", "Danger"]

# Open-Meteo variable name -> silver column name, per source.
WEATHER_COLUMNS = {
    "temperature_2m": "temperature_c",
    "apparent_temperature": "apparent_temp_c",
    "relative_humidity_2m": "humidity_pct",
    "wind_speed_10m": "wind_speed_kmh",
    "wind_gusts_10m": "wind_gust_kmh",
    "precipitation": "precipitation_mm",
    "weather_code": "weather_code",
}
AIR_COLUMNS = {"pm2_5": "pm2_5", "pm10": "pm10", "us_aqi": "us_aqi"}
MARINE_COLUMNS = {"wave_height": "wave_height_m", "wave_period": "wave_period_s"}

DEFAULT_UTC_OFFSET_S = 8 * 3600  # Manila is UTC+8 with no daylight saving

# Heat bands follow PAGASA's heat index classes, folded into three labels:
#   below 33 C   -> Normal   (PAGASA "Caution" 27-32 C is everyday weather in Cebu)
#   33 to 41 C   -> Caution  (PAGASA "Extreme Caution")
#   42 C and up  -> Danger   (PAGASA "Danger" + "Extreme Danger")
HEAT_CAUTION_C = 33.0
HEAT_DANGER_C = 42.0


def heat_category(apparent_temp_c: float | None) -> HeatCategory | None:
    """Map apparent ("feels like") temperature to a heat category; None if unknown."""
    if apparent_temp_c is None:
        return None
    if apparent_temp_c >= HEAT_DANGER_C:
        return "Danger"
    if apparent_temp_c >= HEAT_CAUTION_C:
        return "Caution"
    return "Normal"


def to_utc(local_iso: Any, offset_s: int) -> datetime | None:
    """Convert an API local-time string ('2026-09-29T14:00') to an aware UTC datetime."""
    try:
        naive = datetime.fromisoformat(local_iso)
    except (TypeError, ValueError):
        return None
    return (naive - timedelta(seconds=offset_s)).replace(tzinfo=timezone.utc)


def _at(values: list[Any] | None, i: int) -> Any:
    """values[i], or None when the series is missing or short."""
    if not values or i >= len(values):
        return None
    return values[i]


def _series(body: dict[str, Any] | None, columns: dict[str, str]) -> dict[str, dict[str, Any]]:
    """One source response -> {local_time_string: {silver_column: value}}."""
    if not body:
        return {}
    hourly = body.get("hourly") or {}
    return {
        t: {col: _at(hourly.get(api), i) for api, col in columns.items()}
        for i, t in enumerate(hourly.get("time") or [])
    }


def _offset_s(extract: LocationExtract) -> int:
    """UTC offset the API reported (all sources share the requested timezone)."""
    for body in extract.sources.values():
        try:
            return int(body["utc_offset_seconds"])
        except (KeyError, TypeError, ValueError):
            continue
    return DEFAULT_UTC_OFFSET_S


def flatten_extract(
    extract: LocationExtract,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Turn one location's raw responses into (observation_rows, marine_rows).

    Weather and air quality are merged into one row per hour. Marine rows stay
    separate. A source that failed simply leaves its columns absent (null).
    """
    offset = _offset_s(extract)
    name = extract.location.name

    merged: dict[str, dict[str, Any]] = {}
    for series in (
        _series(extract.sources.get("weather"), WEATHER_COLUMNS),
        _series(extract.sources.get("air_quality"), AIR_COLUMNS),
    ):
        for t, values in series.items():
            merged.setdefault(t, {}).update(values)

    marine = _series(extract.sources.get("marine"), MARINE_COLUMNS)
    obs_rows = [{"location": name, "observed_at": to_utc(t, offset), **v} for t, v in merged.items()]
    marine_rows = [{"location": name, "observed_at": to_utc(t, offset), **v} for t, v in marine.items()]
    return obs_rows, marine_rows


def flatten_all(
    extracts: Sequence[LocationExtract],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Flatten many extracts, keeping their order (later extracts win on duplicates)."""
    obs_rows: list[dict[str, Any]] = []
    marine_rows: list[dict[str, Any]] = []
    for extract in extracts:
        obs, marine = flatten_extract(extract)
        obs_rows.extend(obs)
        marine_rows.extend(marine)
    return obs_rows, marine_rows


def read_raw_file(path: Path) -> LocationExtract:
    """Load one bronze file (as written by extract.save_raw) back into a LocationExtract."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    return LocationExtract(
        location=Location(**doc["location"]),
        fetched_at=datetime.fromisoformat(doc["fetched_at"]),
        sources=doc.get("sources", {}),
        errors=doc.get("errors", {}),
    )


def read_raw_files(raw_dir: Path) -> list[LocationExtract]:
    """Load every bronze file under raw_dir, oldest fetch first; unreadable files are skipped."""
    extracts: list[LocationExtract] = []
    for path in sorted(raw_dir.glob("*/*.json")):
        try:
            extracts.append(read_raw_file(path))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.error("Skipping unreadable raw file %s: %s", path, exc)
    return sorted(extracts, key=lambda e: e.fetched_at)
