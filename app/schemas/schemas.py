"""Pydantic v2 schemas for all API request/response shapes."""
import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ── Location ────────────────────────────────────────────────────────────────

class LocationResolveRequest(BaseModel):
    query: str = Field(..., min_length=1, description="City name, zip code, landmark, or coordinates")


class LocationOut(BaseModel):
    id: uuid.UUID
    resolved_name: str
    country_code: str
    latitude: float
    longitude: float
    timezone: str | None
    has_model_coverage: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Weather Query (CRUD) ─────────────────────────────────────────────────────

class WeatherQueryCreate(BaseModel):
    location_query: str = Field(..., min_length=1)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_date_range(self) -> "WeatherQueryCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days > 365:
            raise ValueError("Date range cannot exceed 365 days")
        return self


class WeatherQueryUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "WeatherQueryUpdate":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class WeatherQueryOut(BaseModel):
    id: uuid.UUID
    location_id: uuid.UUID
    start_date: date
    end_date: date
    temperature_actual: float | None
    temperature_predicted: float | None
    condition_text: str | None
    humidity: float | None
    precip_mm: float | None
    aqi_index: int | None
    pm2_5: float | None
    air_quality: dict[str, Any] | None
    is_anomalous: bool
    anomaly_reason: str | None
    source: str
    created_at: datetime
    updated_at: datetime
    location: LocationOut | None = None

    model_config = {"from_attributes": True}


# ── Weather (live) ───────────────────────────────────────────────────────────

class CurrentWeatherOut(BaseModel):
    location: LocationOut
    temperature_celsius: float
    feels_like_celsius: float
    condition: str
    humidity: float
    wind_kph: float
    pressure_mb: float
    precip_mm: float
    uv_index: float
    aqi_index: int | None
    pm2_5: float | None
    is_anomalous: bool
    anomaly_reason: str | None
    source: str


class ForecastDayOut(BaseModel):
    model_config = {"protected_namespaces": ()}

    date: date
    predicted_temp_c: float
    confidence_lower: float | None
    confidence_upper: float | None
    model_version: str


class ForecastOut(BaseModel):
    location: LocationOut
    forecast: list[ForecastDayOut]


# ── Enrichment ───────────────────────────────────────────────────────────────

class EnrichmentOut(BaseModel):
    location: LocationOut
    country_info: dict[str, Any] | None
    youtube_videos: list[dict[str, Any]]
    maps_embed_url: str | None


# ── Export ───────────────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    format: str = Field(..., pattern="^(json|csv|pdf)$")
    location_id: uuid.UUID | None = None
    start_date: date | None = None
    end_date: date | None = None


# ── About ────────────────────────────────────────────────────────────────────

class AboutOut(BaseModel):
    platform: str
    built_by: str
    assessment: str
    pm_accelerator_mission: str
    github: str


# ── Error ────────────────────────────────────────────────────────────────────

class ErrorOut(BaseModel):
    error: str
    message: str
    status_code: int
