"""SQLAlchemy models matching the Phase 4 schema: locations, weather_queries,
forecast_cache. CHECK constraints enforced at the DB layer as a second line
of defense beyond Pydantic validation in the service layer."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, String,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_longitude_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resolved_name: Mapped[str] = mapped_column(String, nullable=False)
    country_code: Mapped[str] = mapped_column(String, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    has_model_coverage: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    queries: Mapped[list["WeatherQuery"]] = relationship(back_populates="location")
    forecasts: Mapped[list["ForecastCache"]] = relationship(back_populates="location")


class WeatherQuery(Base):
    __tablename__ = "weather_queries"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_date_range_valid"),
        CheckConstraint("humidity IS NULL OR humidity BETWEEN 0 AND 100", name="ck_humidity_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), nullable=False)
    start_date: Mapped[Date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Date] = mapped_column(Date, nullable=False)

    temperature_actual: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_predicted: Mapped[float | None] = mapped_column(Float, nullable=True)
    condition_text: Mapped[str | None] = mapped_column(String, nullable=True)
    humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    precip_mm: Mapped[float | None] = mapped_column(Float, nullable=True)

    aqi_index: Mapped[int | None] = mapped_column(nullable=True)
    pm2_5: Mapped[float | None] = mapped_column(Float, nullable=True)
    air_quality: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    is_anomalous: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    source: Mapped[str] = mapped_column(String, nullable=False)  # 'live_api' | 'forecast_model' | 'historical_dataset'

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    location: Mapped["Location"] = relationship(back_populates="queries")


class ForecastCache(Base):
    __tablename__ = "forecast_cache"
    __table_args__ = (
        UniqueConstraint("location_id", "forecast_date", "model_version", name="uq_forecast_cache_entry"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), nullable=False)
    forecast_date: Mapped[Date] = mapped_column(Date, nullable=False)
    predicted_temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_lower: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_upper: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version: Mapped[str] = mapped_column(String, nullable=False, default="gb_v1")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    location: Mapped["Location"] = relationship(back_populates="forecasts")
