"""Phase 2 (silver, step 2): Pydantic models, validation, dedupe and reject accounting.

Run standalone against the saved bronze files:  python -m pipeline.validate
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Generic, Iterable, Sequence, TypeVar

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from pipeline import config
from pipeline.extract import LocationExtract
from pipeline.transform import HeatCategory, flatten_all, heat_category, read_raw_files

log = logging.getLogger(__name__)

# Physically impossible for Cebu -> the whole row is rejected.
TEMP_MIN_C = 10.0
TEMP_MAX_C = 50.0


class SilverRecord(BaseModel):
    """Fields shared by every silver row, plus the 'not all null' rule."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    # Names of the measurement fields; a row where all of them are null is useless.
    MEASUREMENTS: ClassVar[tuple[str, ...]] = ()

    location: str = Field(min_length=1)
    observed_at: AwareDatetime  # always stored as UTC

    @field_validator("observed_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _not_all_null(self) -> "SilverRecord":
        if all(getattr(self, name) is None for name in self.MEASUREMENTS):
            raise PydanticCustomError("all_null", "record has no measurements")
        return self


class ObservationRecord(SilverRecord):
    """One hour of weather + air quality for one location (nulls allowed per field)."""

    MEASUREMENTS: ClassVar[tuple[str, ...]] = (
        "temperature_c", "apparent_temp_c", "humidity_pct", "wind_speed_kmh",
        "wind_gust_kmh", "precipitation_mm", "weather_code", "pm2_5", "pm10", "us_aqi",
    )

    temperature_c: float | None = Field(default=None, ge=TEMP_MIN_C, le=TEMP_MAX_C)
    apparent_temp_c: float | None = Field(default=None, ge=0, le=70)  # sanity bound
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    wind_speed_kmh: float | None = Field(default=None, ge=0, le=300)
    wind_gust_kmh: float | None = Field(default=None, ge=0, le=400)
    precipitation_mm: float | None = Field(default=None, ge=0, le=500)
    weather_code: int | None = Field(default=None, ge=0, le=99)
    pm2_5: float | None = Field(default=None, ge=0, le=2000)
    pm10: float | None = Field(default=None, ge=0, le=3000)
    us_aqi: int | None = Field(default=None, ge=0, le=500)

    @field_validator("us_aqi", mode="before")
    @classmethod
    def _round_aqi(cls, value: Any) -> Any:
        """AQI is an integer index; tolerate 55.0 or 54.6 from the API."""
        return round(value) if isinstance(value, float) else value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def heat_index_category(self) -> HeatCategory | None:
        """Derived from apparent temperature (see transform.heat_category)."""
        return heat_category(self.apparent_temp_c)


class MarineRecord(SilverRecord):
    """One hour of sea conditions for one coastal location."""

    MEASUREMENTS: ClassVar[tuple[str, ...]] = ("wave_height_m", "wave_period_s")

    wave_height_m: float | None = Field(default=None, ge=0, le=30)
    wave_period_s: float | None = Field(default=None, ge=0, le=40)


T = TypeVar("T", bound=SilverRecord)


@dataclass
class ValidationResult(Generic[T]):
    """Outcome of validating one batch of rows."""

    label: str
    total: int = 0
    records: list[T] = field(default_factory=list)  # valid and de-duplicated
    rejected: Counter[str] = field(default_factory=Counter)  # reason -> row count

    @property
    def rejected_count(self) -> int:
        return sum(self.rejected.values())


def _reason(exc: ValidationError) -> str:
    """Short 'field:problem' label from the first validation error, e.g. 'humidity_pct:above_max'."""
    err = exc.errors()[0]
    where = str(err["loc"][0]) if err["loc"] else "row"
    kind = {"less_than_equal": "above_max", "greater_than_equal": "below_min"}.get(
        err["type"], err["type"]
    )
    return f"{where}:{kind}"


def validate_rows(
    rows: Iterable[dict[str, Any]], model: type[T], label: str
) -> ValidationResult[T]:
    """Validate rows, drop bad ones, dedupe on (location, observed_at), log the tally.

    Later rows win over earlier duplicates, so feed rows oldest-fetch first.
    """
    result: ValidationResult[T] = ValidationResult(label=label)
    latest: dict[tuple[str, datetime], T] = {}
    for row in rows:
        result.total += 1
        try:
            record = model.model_validate(row)
        except ValidationError as exc:
            result.rejected[_reason(exc)] += 1
            continue
        key = (record.location, record.observed_at)
        if key in latest:
            result.rejected["duplicate"] += 1  # the older copy is superseded
        latest[key] = record
    result.records = sorted(latest.values(), key=lambda r: (r.location, r.observed_at))
    _log_result(result)
    return result


def _log_result(result: ValidationResult[Any]) -> None:
    if result.rejected_count:
        log.warning(
            "%s: rejected %d of %d rows -> %s",
            result.label, result.rejected_count, result.total,
            dict(result.rejected.most_common()),
        )
    log.info("%s: %d valid rows kept from %d", result.label, len(result.records), result.total)


@dataclass
class SilverBatch:
    """Validated output of one pipeline run, ready for loading."""

    observations: ValidationResult[ObservationRecord]
    marine: ValidationResult[MarineRecord]

    @property
    def rows_ingested(self) -> int:
        return len(self.observations.records) + len(self.marine.records)

    @property
    def rows_rejected(self) -> int:
        return self.observations.rejected_count + self.marine.rejected_count


def build_silver(extracts: Sequence[LocationExtract]) -> SilverBatch:
    """Bronze extracts -> validated silver records (flatten, validate, dedupe)."""
    obs_rows, marine_rows = flatten_all(extracts)
    return SilverBatch(
        observations=validate_rows(obs_rows, ObservationRecord, "observations"),
        marine=validate_rows(marine_rows, MarineRecord, "marine"),
    )


def main() -> int:
    """CLI: run silver over all saved bronze files and print a summary."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    extracts = read_raw_files(config.RAW_DIR)
    if not extracts:
        log.error("No raw files in %s. Run `python -m pipeline.extract` first.", config.RAW_DIR)
        return 1

    batch = build_silver(extracts)
    obs = batch.observations.records
    heat = Counter(r.heat_index_category for r in obs)
    now = datetime.now(timezone.utc)
    current = [r for r in obs if r.location == "Cebu City" and r.observed_at <= now]

    print(f"\nRaw files read:       {len(extracts)}")
    print(f"Observation rows:     {len(obs)} valid, {batch.observations.rejected_count} rejected")
    print(f"Marine rows:          {len(batch.marine.records)} valid, {batch.marine.rejected_count} rejected")
    print(f"Heat categories:      {dict(heat)}")
    if current:
        print("Latest Cebu City row:")
        print(current[-1].model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
