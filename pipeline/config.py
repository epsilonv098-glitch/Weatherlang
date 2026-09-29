"""Static configuration for the Cebu Pulse pipeline: locations, APIs, tuning knobs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

AreaType = Literal["metro", "mainland", "tourist"]


@dataclass(frozen=True)
class Location:
    """A place in Cebu Province we collect data for."""

    name: str
    area_type: AreaType
    lat: float
    lon: float

    @property
    def slug(self) -> str:
        """File-safe name, e.g. 'Cebu City' -> 'cebu_city'."""
        return self.name.lower().replace(" ", "_")

    @property
    def is_coastal(self) -> bool:
        """Tourist spots are the coastal ones that get marine data."""
        return self.area_type == "tourist"


@dataclass(frozen=True)
class Source:
    """One Open-Meteo endpoint and the hourly variables requested from it."""

    name: str
    url: str
    hourly: tuple[str, ...]
    coastal_only: bool = False  # True -> only fetched for coastal locations


# Coordinates are approximate.
LOCATIONS: tuple[Location, ...] = (
    # Metro Cebu
    Location("Cebu City", "metro", 10.3157, 123.8854),
    Location("Mandaue", "metro", 10.3236, 123.9223),
    Location("Lapu-Lapu", "metro", 10.3103, 123.9494),
    Location("Talisay", "metro", 10.2447, 123.8494),
    # Mainland
    Location("Danao", "mainland", 10.5208, 124.0272),
    Location("Toledo", "mainland", 10.3773, 123.6386),
    Location("Carcar", "mainland", 10.1064, 123.6404),
    Location("Bogo", "mainland", 11.0517, 124.0055),
    # Tourist / coastal
    Location("Moalboal", "tourist", 9.9490, 123.3970),
    Location("Oslob", "tourist", 9.5222, 123.3814),
    Location("Malapascua", "tourist", 11.3339, 124.1120),
    Location("Bantayan", "tourist", 11.1690, 123.7220),
)

# Open-Meteo endpoints (free, no API key). Wind is returned in km/h.
SOURCES: tuple[Source, ...] = (
    Source(
        name="weather",
        url="https://api.open-meteo.com/v1/forecast",
        hourly=(
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "wind_speed_10m",
            "wind_gusts_10m",
            "precipitation",
            "weather_code",
        ),
    ),
    Source(
        name="air_quality",
        url="https://air-quality-api.open-meteo.com/v1/air-quality",
        hourly=("pm2_5", "pm10", "us_aqi"),
    ),
    Source(
        name="marine",
        url="https://marine-api.open-meteo.com/v1/marine",
        hourly=("wave_height", "wave_period"),
        coastal_only=True,
    ),
)

# The API returns local (Manila) time strings; the silver layer converts to UTC.
TIMEZONE = "Asia/Manila"
PAST_DAYS = 1      # re-fetch yesterday so a missed hourly run self-heals
FORECAST_DAYS = 2  # enough lookahead for the 6-hour rain alert

# HTTP behaviour
REQUEST_TIMEOUT_S = 20.0
MAX_RETRIES = 4          # total attempts per request
BACKOFF_BASE_S = 2.0     # waits 2s, 4s, 8s between attempts
REQUEST_PAUSE_S = 0.3    # small courtesy pause between requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
