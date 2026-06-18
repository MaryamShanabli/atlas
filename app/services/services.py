"""
Service layer — all business logic.

Under deadline constraints, consolidated into one file for clarity
rather than splitting across 7 separate files (would be the right call
with more time, but imports and structure are identical either way).
"""
import csv
import io
import uuid
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models_db.models import Location, WeatherQuery
from app.repositories.repositories import ForecastRepository, LocationRepository, QueryRepository
from app.ml import loader

settings = get_settings()

MODEL_VERSION = "gb_v1"


# ── Location resolution ───────────────────────────────────────────────────────

async def resolve_location(query: str, db: Session) -> Location:
    """Geocode raw user input → canonical Location row (create if new)."""
    if not settings.openweathermap_api_key:
        raise HTTPException(503, detail={"error": "api_key_missing",
                                         "message": "OpenWeatherMap API key not configured.",
                                         "status_code": 503})

    url = "http://api.openweathermap.org/geo/1.0/direct"
    params = {"q": query, "limit": 5, "appid": settings.openweathermap_api_key}

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(url, params=params)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(503, detail={"error": "geocoding_failed",
                                             "message": f"Geocoding service unavailable: {e}",
                                             "status_code": 503})

    results = r.json()
    if not results:
        raise HTTPException(404, detail={"error": "location_not_found",
                                         "message": f"Could not find a location matching '{query}'.",
                                         "status_code": 404})

    geo = results[0]
    lat, lon = geo["lat"], geo["lon"]
    repo = LocationRepository(db)
    existing = repo.get_by_coords(lat, lon)
    if existing:
        return existing

    return repo.create(
        resolved_name=geo.get("name", query),
        country_code=geo.get("country", ""),
        latitude=lat,
        longitude=lon,
        timezone=None,
        has_model_coverage=loader.has_model_coverage(lat, lon),
    )


# ── Current weather ───────────────────────────────────────────────────────────

async def get_current_weather(location: Location) -> dict[str, Any]:
    """Fetch live current conditions from OpenWeatherMap. Falls back to
    model-only data with source='forecast_model_fallback' if API is down."""
    if not settings.openweathermap_api_key:
        raise HTTPException(503, detail={"error": "api_key_missing",
                                         "message": "OpenWeatherMap API key not configured.",
                                         "status_code": 503})

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"lat": location.latitude, "lon": location.longitude,
               "appid": settings.openweathermap_api_key, "units": "metric"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
        data = r.json()
        weather = {
            "temperature_celsius": data["main"]["temp"],
            "feels_like_celsius": data["main"]["feels_like"],
            "condition": data["weather"][0]["description"],
            "humidity": data["main"]["humidity"],
            "wind_kph": data["wind"]["speed"] * 3.6,
            "pressure_mb": data["main"]["pressure"],
            "precip_mm": data.get("rain", {}).get("1h", 0.0),
            "uv_index": 0.0,
            "source": "live_api",
        }
    except httpx.HTTPError:
        today = date.today()
        weather = {
            "temperature_celsius": loader.predict_temperature(location.latitude, location.longitude, today),
            "feels_like_celsius": None,
            "condition": "unavailable (API offline)",
            "humidity": None,
            "wind_kph": None,
            "pressure_mb": None,
            "precip_mm": None,
            "uv_index": None,
            "source": "forecast_model_fallback",
        }

    air_quality = await get_air_quality(location)
    weather["aqi_index"] = air_quality.get("aqi_index")
    weather["pm2_5"] = air_quality.get("pm2_5")

    baseline = loader.get_location_baseline(location.resolved_name, location.country_code)
    anomaly = {"is_anomalous": False, "anomaly_reason": None}
    if baseline and weather.get("temperature_celsius"):
        import sys, pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "notebooks"))
        from anomaly_detection import check_anomaly
        anomaly = check_anomaly({
            "temperature_celsius": weather["temperature_celsius"],
            "air_quality_PM2.5": weather.get("pm2_5"),
        }, type("B", (), baseline)())
    weather.update(anomaly)
    return weather


async def get_air_quality(location: Location) -> dict[str, Any]:
    if not settings.openweathermap_api_key:
        return {}
    url = "http://api.openweathermap.org/data/2.5/air_pollution"
    params = {"lat": location.latitude, "lon": location.longitude,
               "appid": settings.openweathermap_api_key}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
        data = r.json()
        components = data["list"][0]["components"]
        aqi = data["list"][0]["main"]["aqi"]
        return {"aqi_index": aqi, "pm2_5": components.get("pm2_5"),
                "air_quality_full": components}
    except Exception:
        return {}


# ── CRUD query service ────────────────────────────────────────────────────────

async def create_query(location_query: str, start_date: date, end_date: date, db: Session) -> WeatherQuery:
    location = await resolve_location(location_query, db)
    today = date.today()
    q_repo = QueryRepository(db)

    temp_actual = None
    temp_predicted = None
    source = "forecast_model"

    if start_date <= today:
        weather = await get_current_weather(location)
        temp_actual = weather.get("temperature_celsius")
        source = weather.get("source", "live_api")
        condition_text = weather.get("condition")
        humidity = weather.get("humidity")
        precip_mm = weather.get("precip_mm")
        aqi_index = weather.get("aqi_index")
        pm2_5 = weather.get("pm2_5")
        is_anomalous = weather.get("is_anomalous", False)
        anomaly_reason = weather.get("anomaly_reason")
    else:
        condition_text = None
        humidity = None
        precip_mm = None
        aqi_index = None
        pm2_5 = None
        is_anomalous = False
        anomaly_reason = None

    mid_date = start_date + (end_date - start_date) / 2
    if isinstance(mid_date, timedelta):
        mid_date = start_date + timedelta(days=(end_date - start_date).days // 2)
    temp_predicted = loader.predict_temperature(location.latitude, location.longitude, mid_date)
    if temp_actual is None:
        source = "forecast_model"

    return q_repo.create(
        location_id=location.id,
        start_date=start_date,
        end_date=end_date,
        temperature_actual=temp_actual,
        temperature_predicted=temp_predicted,
        condition_text=condition_text,
        humidity=humidity,
        precip_mm=precip_mm,
        aqi_index=aqi_index,
        pm2_5=pm2_5,
        air_quality=None,
        is_anomalous=is_anomalous,
        anomaly_reason=anomaly_reason,
        source=source,
    )


# ── Forecast service ──────────────────────────────────────────────────────────

def get_forecast(location: Location, days: int, db: Session) -> list[dict]:
    f_repo = ForecastRepository(db)
    results = []
    for i in range(days):
        target = date.today() + timedelta(days=i)
        cached = f_repo.get_cached(location.id, target, MODEL_VERSION)
        if not cached:
            pred = loader.predict_temperature(location.latitude, location.longitude, target)
            cached = f_repo.create(
                location_id=location.id,
                forecast_date=target,
                predicted_temp_c=pred,
                confidence_lower=round(pred - 2.5, 2),
                confidence_upper=round(pred + 2.5, 2),
                model_version=MODEL_VERSION,
            )
        results.append({
            "date": cached.forecast_date,
            "predicted_temp_c": cached.predicted_temp_c,
            "confidence_lower": cached.confidence_lower,
            "confidence_upper": cached.confidence_upper,
            "model_version": cached.model_version,
        })
    return results


# ── Enrichment service ────────────────────────────────────────────────────────

async def get_enrichment(location: Location) -> dict[str, Any]:
    country_info = await _get_country_info(location.country_code)
    youtube_videos = await _get_youtube_videos(location.resolved_name)
    maps_url = _get_maps_embed_url(location)
    return {
        "location": location,
        "country_info": country_info,
        "youtube_videos": youtube_videos,
        "maps_embed_url": maps_url,
    }


async def _get_country_info(country_code: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://restcountries.com/v3.1/alpha/{country_code}")
            r.raise_for_status()
        data = r.json()
        c = data[0]
        return {
            "name": c["name"]["common"],
            "capital": c.get("capital", [None])[0],
            "region": c.get("region"),
            "population": c.get("population"),
            "currencies": list(c.get("currencies", {}).keys()),
            "languages": list(c.get("languages", {}).values()),
        }
    except Exception:
        return None


async def _get_youtube_videos(location_name: str) -> list[dict]:
    if not settings.youtube_api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "q": f"{location_name} weather travel",
                    "part": "snippet",
                    "type": "video",
                    "maxResults": 3,
                    "key": settings.youtube_api_key,
                },
            )
            r.raise_for_status()
        items = r.json().get("items", [])
        return [
            {
                "title": i["snippet"]["title"],
                "video_id": i["id"]["videoId"],
                "url": f"https://www.youtube.com/watch?v={i['id']['videoId']}",
                "thumbnail": i["snippet"]["thumbnails"]["default"]["url"],
            }
            for i in items
        ]
    except Exception:
        return []


def _get_maps_embed_url(location: Location) -> str | None:
    if not settings.google_maps_api_key:
        return None
    return (
        f"https://www.google.com/maps/embed/v1/place"
        f"?key={settings.google_maps_api_key}"
        f"&q={location.latitude},{location.longitude}"
        f"&zoom=10"
    )


# ── Export service ────────────────────────────────────────────────────────────

def export_queries(queries: list[WeatherQuery], fmt: str) -> tuple[bytes, str]:
    """Returns (content_bytes, media_type)."""
    if fmt == "json":
        import json
        from app.schemas.schemas import WeatherQueryOut
        data = [WeatherQueryOut.model_validate(q).model_dump(mode="json") for q in queries]
        return json.dumps(data, indent=2, default=str).encode(), "application/json"

    elif fmt == "csv":
        buf = io.StringIO()
        if queries:
            fields = ["id", "location_id", "start_date", "end_date",
                      "temperature_actual", "temperature_predicted",
                      "condition_text", "humidity", "precip_mm",
                      "aqi_index", "pm2_5", "is_anomalous", "source",
                      "created_at"]
            writer = csv.DictWriter(buf, fieldnames=fields)
            writer.writeheader()
            for q in queries:
                writer.writerow({f: getattr(q, f, None) for f in fields})
        return buf.getvalue().encode(), "text/csv"

    elif fmt == "pdf":
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from reportlab.lib import colors

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph("Atlas Weather Intelligence Platform", styles["Title"]))
        elements.append(Paragraph("PM Accelerator AI Engineer Internship Assessment", styles["Heading2"]))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(
            "PM Accelerator Mission: Empower aspiring product managers with the skills, "
            "network, and experience to accelerate their PM career.", styles["Normal"]))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(f"Export generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]))
        elements.append(Spacer(1, 12))

        if queries:
            headers = ["Location ID", "Start Date", "End Date", "Temp Actual", "Temp Predicted", "Source", "Anomalous"]
            rows = [headers] + [
                [str(q.location_id)[:8] + "...", str(q.start_date), str(q.end_date),
                 f"{q.temperature_actual:.1f}°C" if q.temperature_actual else "—",
                 f"{q.temperature_predicted:.1f}°C" if q.temperature_predicted else "—",
                 q.source, "YES" if q.is_anomalous else "no"]
                for q in queries
            ]
            t = Table(rows)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d6a9f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
            ]))
            elements.append(t)

        doc.build(elements)
        return buf.getvalue(), "application/pdf"

    raise ValueError(f"Unsupported format: {fmt}")
