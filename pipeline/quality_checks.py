"""Phase 4: quality gate that runs on the validated batch BEFORE anything is loaded.

A run fails (and loads nothing) if any blocking check fails:
  * freshness: the newest observation at or before now is older than 3 hours
  * null rate: more than 10% of weather/air values are null
  * coverage:  fewer than 10 of the 12 locations returned data
The marine null rate is only logged as a warning (sea data is patchier).
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Sequence

from pipeline.config import LOCATIONS
from pipeline.transform import AIR_COLUMNS, MARINE_COLUMNS, WEATHER_COLUMNS

if TYPE_CHECKING:  # type hints only; keeps this module importable without pydantic
    from pipeline.validate import SilverBatch

log = logging.getLogger(__name__)

MAX_AGE = timedelta(hours=3)
MAX_NULL_RATE = 0.10
MIN_LOCATIONS = 10

# Which fields count toward the null rate (same names the silver layer uses).
OBS_FIELDS = (*WEATHER_COLUMNS.values(), *AIR_COLUMNS.values())
MARINE_FIELDS = tuple(MARINE_COLUMNS.values())


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one check, with a human-readable detail line."""

    name: str
    passed: bool
    detail: str


class QualityCheckError(Exception):
    """Raised when one or more blocking checks fail."""

    def __init__(self, failures: Sequence[CheckResult]) -> None:
        self.failures = list(failures)
        summary = "; ".join(f"{f.name}: {f.detail}" for f in self.failures)
        super().__init__(f"quality checks failed -> {summary}")


def check_freshness(
    records: Sequence[Any], now: datetime, max_age: timedelta = MAX_AGE
) -> CheckResult:
    """Newest observation at or before `now` must be at most `max_age` old.

    Forecast hours (in the future) are ignored: they say nothing about freshness.
    """
    observed = [r.observed_at for r in records if r.observed_at <= now]
    limit_h = max_age.total_seconds() / 3600
    if not observed:
        return CheckResult("freshness", False, "no observations at or before now")
    age_h = (now - max(observed)).total_seconds() / 3600
    return CheckResult(
        "freshness", age_h <= limit_h, f"newest observation is {age_h:.1f}h old (limit {limit_h:.0f}h)"
    )


def null_rates(records: Sequence[Any], fields: Sequence[str]) -> tuple[float, dict[str, float]]:
    """Overall and per-field share of null values. No records counts as 100% null."""
    if not records or not fields:
        return 1.0, {f: 1.0 for f in fields}
    nulls: Counter[str] = Counter()
    for record in records:
        for name in fields:
            if getattr(record, name, None) is None:
                nulls[name] += 1
    per_field = {name: nulls[name] / len(records) for name in fields}
    overall = sum(nulls.values()) / (len(records) * len(fields))
    return overall, per_field


def check_null_rate(
    records: Sequence[Any], fields: Sequence[str] = OBS_FIELDS, max_rate: float = MAX_NULL_RATE
) -> CheckResult:
    """Share of null weather/air values must be at most `max_rate`."""
    overall, per_field = null_rates(records, fields)
    worst_name, worst_rate = max(per_field.items(), key=lambda item: item[1])
    return CheckResult(
        "null_rate",
        overall <= max_rate,
        f"{overall:.1%} of values are null (limit {max_rate:.0%}); worst field {worst_name} at {worst_rate:.1%}",
    )


def check_coverage(
    records: Sequence[Any],
    expected: Sequence[str] = tuple(loc.name for loc in LOCATIONS),
    min_locations: int = MIN_LOCATIONS,
) -> CheckResult:
    """At least `min_locations` of the expected locations must have returned data."""
    seen = {r.location for r in records}
    got = [name for name in expected if name in seen]
    missing = [name for name in expected if name not in seen]
    detail = f"{len(got)} of {len(expected)} locations returned data (need {min_locations})"
    if missing:
        detail += f"; missing: {', '.join(missing)}"
    return CheckResult("coverage", len(got) >= min_locations, detail)


def run_checks(batch: "SilverBatch", now: datetime | None = None) -> list[CheckResult]:
    """Run every blocking check and log each result. Never raises."""
    now = now or datetime.now(timezone.utc)
    records = batch.observations.records
    results = [
        check_freshness(records, now),
        check_null_rate(records),
        check_coverage(records),
    ]
    for result in results:
        log.log(
            logging.INFO if result.passed else logging.ERROR,
            "quality check %-9s %s - %s", result.name, "PASS" if result.passed else "FAIL", result.detail,
        )

    marine = batch.marine.records
    if marine:
        overall, _ = null_rates(marine, MARINE_FIELDS)
        if overall > MAX_NULL_RATE:
            log.warning("marine data is %.1f%% null (informational, not blocking)", overall * 100)
    return results


def enforce(batch: "SilverBatch", now: datetime | None = None) -> list[CheckResult]:
    """Run the checks; raise QualityCheckError if any blocking check failed."""
    results = run_checks(batch, now)
    failures = [r for r in results if not r.passed]
    if failures:
        raise QualityCheckError(failures)
    return results
