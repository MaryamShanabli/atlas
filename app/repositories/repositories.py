"""Database access layer. No business logic here — only queries and writes."""
import uuid
from datetime import date

from sqlalchemy.orm import Session, joinedload

from app.models_db.models import ForecastCache, Location, WeatherQuery


# ── Location ─────────────────────────────────────────────────────────────────

class LocationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_coords(self, lat: float, lon: float) -> Location | None:
        lat_r, lon_r = round(lat, 2), round(lon, 2)
        return (
            self.db.query(Location)
            .filter(
                Location.latitude.between(lat_r - 0.01, lat_r + 0.01),
                Location.longitude.between(lon_r - 0.01, lon_r + 0.01),
            )
            .first()
        )

    def get_by_id(self, location_id: uuid.UUID) -> Location | None:
        return self.db.query(Location).filter(Location.id == location_id).first()

    def create(self, **kwargs) -> Location:
        loc = Location(**kwargs)
        self.db.add(loc)
        self.db.commit()
        self.db.refresh(loc)
        return loc

    def list_all(self) -> list[Location]:
        return self.db.query(Location).all()


# ── WeatherQuery ──────────────────────────────────────────────────────────────

class QueryRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> WeatherQuery:
        q = WeatherQuery(**kwargs)
        self.db.add(q)
        self.db.commit()
        self.db.refresh(q)
        return q

    def get_by_id(self, query_id: uuid.UUID) -> WeatherQuery | None:
        return (
            self.db.query(WeatherQuery)
            .options(joinedload(WeatherQuery.location))
            .filter(WeatherQuery.id == query_id)
            .first()
        )

    def list_all(
        self,
        location_id: uuid.UUID | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> list[WeatherQuery]:
        q = self.db.query(WeatherQuery).options(joinedload(WeatherQuery.location))
        if location_id:
            q = q.filter(WeatherQuery.location_id == location_id)
        if start_date:
            q = q.filter(WeatherQuery.start_date >= start_date)
        if end_date:
            q = q.filter(WeatherQuery.end_date <= end_date)
        return q.order_by(WeatherQuery.created_at.desc()).limit(limit).all()

    def update(self, query_id: uuid.UUID, updates: dict) -> WeatherQuery | None:
        q = self.db.query(WeatherQuery).filter(WeatherQuery.id == query_id).first()
        if not q:
            return None
        for key, val in updates.items():
            if val is not None:
                setattr(q, key, val)
        self.db.commit()
        self.db.refresh(q)
        return q

    def delete(self, query_id: uuid.UUID) -> bool:
        q = self.db.query(WeatherQuery).filter(WeatherQuery.id == query_id).first()
        if not q:
            return False
        self.db.delete(q)
        self.db.commit()
        return True


# ── ForecastCache ─────────────────────────────────────────────────────────────

class ForecastRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_cached(self, location_id: uuid.UUID, forecast_date: date, model_version: str) -> ForecastCache | None:
        return (
            self.db.query(ForecastCache)
            .filter(
                ForecastCache.location_id == location_id,
                ForecastCache.forecast_date == forecast_date,
                ForecastCache.model_version == model_version,
            )
            .first()
        )

    def create(self, **kwargs) -> ForecastCache:
        fc = ForecastCache(**kwargs)
        self.db.add(fc)
        self.db.commit()
        self.db.refresh(fc)
        return fc

    def list_for_location(self, location_id: uuid.UUID) -> list[ForecastCache]:
        return (
            self.db.query(ForecastCache)
            .filter(ForecastCache.location_id == location_id)
            .order_by(ForecastCache.forecast_date)
            .all()
        )
