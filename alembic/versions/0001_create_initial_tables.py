"""create initial tables

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("resolved_name", sa.String(), nullable=False),
        sa.Column("country_code", sa.String(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=True),
        sa.Column("has_model_coverage", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_latitude_range"),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_longitude_range"),
    )
    op.create_index("ix_locations_latlon", "locations", ["latitude", "longitude"])

    op.create_table(
        "weather_queries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("temperature_actual", sa.Float(), nullable=True),
        sa.Column("temperature_predicted", sa.Float(), nullable=True),
        sa.Column("condition_text", sa.String(), nullable=True),
        sa.Column("humidity", sa.Float(), nullable=True),
        sa.Column("precip_mm", sa.Float(), nullable=True),
        sa.Column("aqi_index", sa.Integer(), nullable=True),
        sa.Column("pm2_5", sa.Float(), nullable=True),
        sa.Column("air_quality", JSONB(), nullable=True),
        sa.Column("is_anomalous", sa.Boolean(), default=False),
        sa.Column("anomaly_reason", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("end_date >= start_date", name="ck_date_range_valid"),
        sa.CheckConstraint("humidity IS NULL OR humidity BETWEEN 0 AND 100", name="ck_humidity_range"),
    )
    op.create_index("ix_weather_queries_location_dates", "weather_queries",
                    ["location_id", "start_date", "end_date"])

    op.create_table(
        "forecast_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("predicted_temp_c", sa.Float(), nullable=False),
        sa.Column("confidence_lower", sa.Float(), nullable=True),
        sa.Column("confidence_upper", sa.Float(), nullable=True),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("location_id", "forecast_date", "model_version",
                            name="uq_forecast_cache_entry"),
    )


def downgrade() -> None:
    op.drop_table("forecast_cache")
    op.drop_table("weather_queries")
    op.drop_table("locations")
