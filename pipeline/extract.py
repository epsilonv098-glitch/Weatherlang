"""Phase 1 (bronze): pull raw Open-Meteo JSON and save it untouched.

Run standalone with:  python -m pipeline.extract
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import requests

from pipeline import config
from pipeline.config import LOCATIONS, SOURCES, Location

log = logging.getLogger(__name__)

# Rate limiting and transient server errors are worth retrying; other 4xx are not.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ExtractError(Exception):
    """A source could not be fetched (after retries where retrying makes sense)."""


@dataclass
class LocationExtract:
    """Everything fetched for one location in one run."""

    location: Location
    fetched_at: datetime  # UTC
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)  # name -> raw JSON
    errors: dict[str, str] = field(default_factory=dict)  # name -> failure message

    @property
    def has_data(self) -> bool:
        """At least one source succeeded."""
        return bool(self.sources)

    @property
    def ok(self) -> bool:
        """Every requested source succeeded."""
        return self.has_data and not self.errors


def _reason(resp: requests.Response) -> str:
    """Pull Open-Meteo's error reason out of a failed response, if present."""
    try:
        return str(resp.json().get("reason", "no reason given"))
    except (ValueError, AttributeError):
        return "no reason given"


def _validated(body: Any) -> dict[str, Any]:
    """Confirm a 200 response really carries an hourly time series."""
    if not isinstance(body, dict) or body.get("error"):
        reason = body.get("reason") if isinstance(body, dict) else "unexpected body"
        raise ExtractError(f"API returned an error body: {reason}")
    if "time" not in (body.get("hourly") or {}):
        raise ExtractError("response has no hourly.time series")
    return body


def fetch_json(
    session: requests.Session, url: str, params: dict[str, Any]
) -> dict[str, Any]:
    """GET a URL and return validated JSON, retrying transient failures with backoff."""
    last_error = "unknown error"
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=config.REQUEST_TIMEOUT_S)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        else:
            if resp.status_code == 200:
                try:
                    return _validated(resp.json())
                except ValueError:  # truncated/garbled body: treat as transient
                    last_error = "response body was not valid JSON"
            elif resp.status_code in RETRYABLE_STATUS:
                last_error = f"HTTP {resp.status_code}"
            else:  # e.g. 400 bad parameter: retrying cannot help
                raise ExtractError(f"HTTP {resp.status_code}: {_reason(resp)}")

        if attempt < config.MAX_RETRIES:
            delay = config.BACKOFF_BASE_S * 2 ** (attempt - 1)
            log.warning(
                "Attempt %d/%d failed (%s); retrying in %.0fs",
                attempt, config.MAX_RETRIES, last_error, delay,
            )
            time.sleep(delay)
    raise ExtractError(f"gave up after {config.MAX_RETRIES} attempts: {last_error}")


def extract_location(
    session: requests.Session, loc: Location, fetched_at: datetime
) -> LocationExtract:
    """Fetch every applicable source for one location; a failed source is recorded, not fatal."""
    result = LocationExtract(location=loc, fetched_at=fetched_at)
    for src in SOURCES:
        if src.coastal_only and not loc.is_coastal:
            continue
        params = {
            "latitude": loc.lat,
            "longitude": loc.lon,
            "hourly": ",".join(src.hourly),
            "timezone": config.TIMEZONE,
            "past_days": config.PAST_DAYS,
            "forecast_days": config.FORECAST_DAYS,
        }
        try:
            result.sources[src.name] = fetch_json(session, src.url, params)
        except ExtractError as exc:
            result.errors[src.name] = str(exc)
            log.error("%s / %s failed: %s", loc.name, src.name, exc)
        time.sleep(config.REQUEST_PAUSE_S)
    return result


def raw_path(loc: Location, fetched_at: datetime, raw_dir: Path) -> Path:
    """data/raw/YYYY-MM-DD/HHmm_location.json (date and time in UTC)."""
    return raw_dir / f"{fetched_at:%Y-%m-%d}" / f"{fetched_at:%H%M}_{loc.slug}.json"


def save_raw(result: LocationExtract, raw_dir: Path) -> Path | None:
    """Write the bronze file for a location. Returns None if nothing was fetched."""
    if not result.has_data:
        return None
    path = raw_path(result.location, result.fetched_at, raw_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "location": {
            "name": result.location.name,
            "area_type": result.location.area_type,
            "lat": result.location.lat,
            "lon": result.location.lon,
        },
        "fetched_at": result.fetched_at.isoformat(),
        "sources": result.sources,  # untouched API responses
        "errors": result.errors,
    }
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def run_extraction(
    locations: Sequence[Location] = LOCATIONS,
    raw_dir: Path = config.RAW_DIR,
    session: requests.Session | None = None,
    now: datetime | None = None,
) -> list[LocationExtract]:
    """Extract all locations and write their raw files. Never raises on API failures."""
    fetched_at = now or datetime.now(timezone.utc)
    owns_session = session is None
    if session is None:
        session = requests.Session()
        session.headers["User-Agent"] = "cebu-pulse/0.1 (portfolio project)"

    results: list[LocationExtract] = []
    try:
        for loc in locations:
            result = extract_location(session, loc, fetched_at)
            path = save_raw(result, raw_dir)
            log.info(
                "%-11s sources=%s errors=%d -> %s",
                loc.name, sorted(result.sources), len(result.errors), path or "no file",
            )
            results.append(result)
    finally:
        if owns_session:
            session.close()
    return results


def main() -> int:
    """CLI entry point: extract everything, print a summary, exit 1 if any location is empty."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    results = run_extraction()
    with_data = sum(r.has_data for r in results)
    fully_ok = sum(r.ok for r in results)
    log.info(
        "Extract done: %d/%d locations with data, %d fully ok",
        with_data, len(results), fully_ok,
    )
    return 0 if with_data == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

