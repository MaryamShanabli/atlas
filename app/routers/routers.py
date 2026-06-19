"""All API routers. Registered on the main app in app/main.py."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.repositories import LocationRepository, QueryRepository
from app.schemas.schemas import (
    AboutOut, CurrentWeatherOut, EnrichmentOut, ExportRequest,
    ForecastOut, LocationOut, LocationResolveRequest, WeatherQueryCreate,
    WeatherQueryOut, WeatherQueryUpdate,
)
from app.services import services

# ── Weather ───────────────────────────────────────────────────────────────────
weather_router = APIRouter(prefix="/weather", tags=["weather"])


@weather_router.get("/current", response_model=CurrentWeatherOut)
async def current_weather(location: str = Query(..., description="Location query string"),
                          db: Session = Depends(get_db)):
    loc = await services.resolve_location(location, db)
    weather = await services.get_current_weather(loc)
    return {**weather, "location": loc}


@weather_router.get("/forecast", response_model=ForecastOut)
async def forecast(location: str = Query(...), days: int = Query(7, ge=1, le=14),
                   db: Session = Depends(get_db)):
    loc = await services.resolve_location(location, db)
    forecast_data = services.get_forecast(loc, days, db)
    return {"location": loc, "forecast": forecast_data}


# ── Locations ────────────────────────────────────────────────────────────────
location_router = APIRouter(prefix="/locations", tags=["locations"])


@location_router.post("/resolve", response_model=LocationOut)
async def resolve_location(body: LocationResolveRequest, db: Session = Depends(get_db)):
    return await services.resolve_location(body.query, db)


@location_router.get("", response_model=list[LocationOut])
def list_locations(db: Session = Depends(get_db)):
    return LocationRepository(db).list_all()


@location_router.get("/{location_id}", response_model=LocationOut)
def get_location(location_id: uuid.UUID, db: Session = Depends(get_db)):
    loc = LocationRepository(db).get_by_id(location_id)
    if not loc:
        raise HTTPException(404, detail={"error": "not_found", "message": "Location not found.", "status_code": 404})
    return loc


# ── CRUD Queries ──────────────────────────────────────────────────────────────
query_router = APIRouter(prefix="/queries", tags=["queries"])


@query_router.post("", response_model=WeatherQueryOut, status_code=201)
async def create_query(body: WeatherQueryCreate, db: Session = Depends(get_db)):
    return await services.create_query(body.location_query, body.start_date, body.end_date, db)


@query_router.get("", response_model=list[WeatherQueryOut])
def list_queries(
    location_id: uuid.UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return QueryRepository(db).list_all(location_id=location_id,
                                         start_date=start_date,
                                         end_date=end_date,
                                         limit=limit)


@query_router.get("/{query_id}", response_model=WeatherQueryOut)
def get_query(query_id: uuid.UUID, db: Session = Depends(get_db)):
    q = QueryRepository(db).get_by_id(query_id)
    if not q:
        raise HTTPException(404, detail={"error": "not_found", "message": "Query not found.", "status_code": 404})
    return q


@query_router.put("/{query_id}", response_model=WeatherQueryOut)
def update_query(query_id: uuid.UUID, body: WeatherQueryUpdate, db: Session = Depends(get_db)):
    updates = body.model_dump(exclude_none=True)
    q = QueryRepository(db).update(query_id, updates)
    if not q:
        raise HTTPException(404, detail={"error": "not_found", "message": "Query not found.", "status_code": 404})
    return q


@query_router.delete("/{query_id}", status_code=204)
def delete_query(query_id: uuid.UUID, db: Session = Depends(get_db)):
    deleted = QueryRepository(db).delete(query_id)
    if not deleted:
        raise HTTPException(404, detail={"error": "not_found", "message": "Query not found.", "status_code": 404})


# ── Export ────────────────────────────────────────────────────────────────────
@query_router.get("/export/data")
def export_queries(
    format: str = Query(..., pattern="^(json|csv|pdf)$"),
    location_id: uuid.UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    queries = QueryRepository(db).list_all(location_id=location_id,
                                            start_date=start_date,
                                            end_date=end_date,
                                            limit=500)
    content, media_type = services.export_queries(queries, format)
    ext = {"json": "json", "csv": "csv", "pdf": "pdf"}[format]
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f"attachment; filename=atlas_export.{ext}"})


# ── Forecast (ML direct) ──────────────────────────────────────────────────────
forecast_router = APIRouter(prefix="/forecast", tags=["forecast"])


@forecast_router.get("/{location_id}", response_model=ForecastOut)
def get_forecast_by_id(location_id: uuid.UUID, days: int = Query(7, ge=1, le=14),
                        db: Session = Depends(get_db)):
    loc = LocationRepository(db).get_by_id(location_id)
    if not loc:
        raise HTTPException(404, detail={"error": "not_found", "message": "Location not found.", "status_code": 404})
    forecast_data = services.get_forecast(loc, days, db)
    return {"location": loc, "forecast": forecast_data}


# ── Anomaly check ─────────────────────────────────────────────────────────────
anomaly_router = APIRouter(prefix="/anomaly-check", tags=["anomaly"])


@anomaly_router.get("/{location_id}")
async def anomaly_check(location_id: uuid.UUID, db: Session = Depends(get_db)):
    loc = LocationRepository(db).get_by_id(location_id)
    if not loc:
        raise HTTPException(404, detail={"error": "not_found", "message": "Location not found.", "status_code": 404})
    weather = await services.get_current_weather(loc)
    return {
        "location": LocationOut.model_validate(loc),
        "is_anomalous": weather.get("is_anomalous", False),
        "anomaly_reason": weather.get("anomaly_reason"),
        "temperature_celsius": weather.get("temperature_celsius"),
    }


# ── Enrichment ────────────────────────────────────────────────────────────────
enrich_router = APIRouter(prefix="/enrich", tags=["enrichment"])


@enrich_router.get("/{location_id}", response_model=EnrichmentOut)
async def enrich(location_id: uuid.UUID, db: Session = Depends(get_db)):
    loc = LocationRepository(db).get_by_id(location_id)
    if not loc:
        raise HTTPException(404, detail={"error": "not_found", "message": "Location not found.", "status_code": 404})
    return await services.get_enrichment(loc)


# ── About ─────────────────────────────────────────────────────────────────────
about_router = APIRouter(prefix="/about", tags=["system"])


@about_router.get("", response_model=AboutOut)
def about():
    return {
        "platform": "Atlas Weather Intelligence Platform",
        "built_by": "Maryam Shanabli — PM Accelerator AI Engineer Internship Assessment",
        "assessment": "Dual Role: Backend Engineer + Data Science",
        "pm_accelerator_mission": (
            "PM Accelerator is the world's most accessible product management program, "
            "providing aspiring and experienced PMs with the skills, mentorship, and "
            "real-world experience needed to land and excel in product management roles."
        ),
        "github": "https://github.com/MaryamShanabli/atlas",
    }
