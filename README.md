# Atlas — Weather Intelligence Platform

**PM Accelerator AI Engineer Internship Assessment — Dual Role (Backend Engineer + Data Science)**

**Candidate:** Maryam Shanabli
**Demo video:** _PUT LINK HERE_

Atlas resolves any location string (city, zip, landmark, or raw coordinates) to canonical coordinates via geocoding, then layers live weather, a trained forecasting model, statistical anomaly detection, and third-party enrichment (country facts, YouTube, Google Maps) on top — all backed by PostgreSQL and exposed as a documented REST API.

## About PM Accelerator

PM Accelerator is the world's most accessible product management program, providing aspiring and experienced PMs with the skills, mentorship, and real-world experience needed to land and excel in product management roles. This assessment's "dual role" format — building a real backend service *and* the data science behind it — mirrors the cross-functional work PMs are expected to drive in industry.

## Architecture

```
Client (Swagger UI at /docs)
        │
        ▼
   FastAPI app (app/main.py)
        │
   ┌────┴─────┬──────────────┬───────────────┐
   ▼           ▼              ▼               ▼
routers/    services/     repositories/    ml/loader.py
(14 routes) (business     (DB access,     (loads 3 .joblib
             logic, 3rd-   SQLAlchemy)     artifacts once
             party APIs)                   at startup)
        │                       │
        ▼                       ▼
  OpenWeatherMap,          PostgreSQL
  YouTube, Google Maps,    (locations, weather_queries,
  Rest Countries           forecast_cache)
```

**Location resolution is always geocoding-first.** Every endpoint that accepts a free-text location calls the OpenWeatherMap Geocoding API to resolve it to canonical lat/long before anything else happens — live weather lookup, forecast generation, and DB writes all key off that canonical coordinate, not the raw input string.

**Every weather reading is tagged with its `source`:** `live_api` (OpenWeatherMap current conditions), `forecast_model` (this project's trained gradient boosting model), or `historical_dataset` (the Global Weather Repository training data). A reviewer can always tell where a number came from.

**Errors are always the same shape:**
```json
{"error": "not_found", "message": "Location not found.", "status_code": 404}
```

## Data model

Three tables, defined in `app/models_db/models.py`, created by `alembic/versions/0001_create_initial_tables.py`:

- **`locations`** — canonical resolved locations (lat/long, country code, timezone). `has_model_coverage` is `True` when this location's rounded coordinates were part of the forecasting model's training set (see the notebook, Section 6) — it tells you whether a forecast for this place comes from real historical baselines or pure lat/long/seasonality extrapolation.
- **`weather_queries`** — every weather lookup ever made (CRUD-able), with the `source` field above plus optional anomaly flags.
- **`forecast_cache`** — cached model predictions per `(location, date, model_version)`, so repeated forecast requests don't re-run inference unnecessarily.

## The forecasting model

A gradient boosting regressor (scikit-learn), trained on the [Global Weather Repository](https://www.kaggle.com/datasets/nelgiriyewithana/global-weather-repository) dataset, predicting temperature from `latitude`, `longitude`, and day-of-year (encoded as `sin`/`cos` to avoid a discontinuity at the year boundary). Because it uses geographic coordinates rather than a per-city lookup table, it produces an estimate for *any* lat/long — not just the cities in the training set.

It's evaluated against a seasonal-naive baseline (predict each location's historical mean temperature for that day-of-year) — the bar any real model has to clear to be worth deploying. Full methodology, EDA, the two-pronged data cleaning approach, the anomaly-detection baselines, and the model comparison are all in **`notebooks/01_atlas_notebook.ipynb`**, which is the data-science deliverable for this assessment and reproduces the exact `.joblib` artifacts the API loads at startup.

Model artifacts live in `models/` and are loaded once at FastAPI startup by `app/ml/loader.py`:
- `forecast_model.joblib` — `{"model": ..., "features": [...]}`
- `location_baselines.joblib` — per-location mean/std for temperature and PM2.5, used for anomaly detection
- `known_coverage_coords.joblib` — the set of coordinates the model was actually trained on (backs `has_model_coverage`)

## Setup

**Requirements:** Docker and Docker Compose. Python 3.12 only needed if you want to run the notebook or tests outside Docker.

1. **Environment variables.** Copy the template and fill in real values:
   ```bash
   cp .env.example .env
   ```
   At minimum, get a free OpenWeatherMap key at https://openweathermap.org/api (instant signup) and set `OPENWEATHERMAP_API_KEY`. The app boots and serves `/health`, `/locations`, `/queries`, and `/about` without any third-party keys — `YOUTUBE_API_KEY` and `GOOGLE_MAPS_API_KEY` are only required for `/enrich/{location_id}`, and that endpoint degrades gracefully (returns what it can, omits what it can't) if a key is missing.

2. **Build and start everything:**
   ```bash
   docker-compose up -d --build
   ```
   `--build` matters here even on a re-run if `Dockerfile` or `requirements.txt` changed (e.g. system packages for PDF export) — `docker-compose up -d` alone won't pick up Dockerfile changes, only `restart` of an *already-built* image.

3. **Run database migrations** (creates the three tables):
   ```bash
   docker-compose exec api alembic upgrade head
   ```
   Expected output: `Running upgrade  -> 0001, create initial tables`

4. **Verify.** Open http://localhost:8000/docs — you should see all 14 endpoints grouped by tag (weather, locations, queries, forecast, anomaly, enrichment, system). `http://localhost:8000/health` should return `{"status": "ok", "database": "connected"}`.

5. **Try a live call** in Swagger UI: `GET /weather/current?location=London` should return live temperature, sourced from OpenWeatherMap.

### If something doesn't come up

`docker-compose logs --tail=80 api` is the first thing to check — it'll show a Python traceback if the app failed to start. If a container is stuck mid-restart for more than ~30 seconds, prefer a clean recreate over waiting on `restart`:
```bash
docker-compose down
docker-compose up -d --build
```

### Running tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```
(`tests/conftest.py` uses `TEST_DATABASE_URL` from `.env`, pointed at `localhost` instead of the Docker-internal `db` hostname, since pytest runs on the host.)

### Running the notebook

```bash
pip install -r requirements.txt -r requirements-dev.txt
jupyter notebook notebooks/01_atlas_notebook.ipynb
```
Requires the raw CSV at `notebooks/data/GlobalWeatherRepository.csv` (download from the Kaggle link above — not committed to the repo due to size).

## API reference

All 14 endpoints are documented interactively at `/docs` — that's the intended demo surface, there is no separate frontend. Summary:

| Method & path | Purpose |
|---|---|
| `GET /health` | DB connectivity check |
| `GET /weather/current?location=` | Live current conditions for any location string (geocodes first) |
| `GET /weather/forecast?location=&days=` | N-day forecast for any location string |
| `POST /locations/resolve` | Geocode a location string to canonical lat/long, persisting it |
| `GET /locations` | List all previously resolved locations |
| `GET /locations/{id}` | Fetch one resolved location |
| `POST /queries` | Create a weather query record (resolves location, fetches/stores weather) |
| `GET /queries` | List query history, filterable by location/date range |
| `GET /queries/{id}` | Fetch one query record |
| `PUT /queries/{id}` | Update a query's date range |
| `DELETE /queries/{id}` | Delete a query record |
| `GET /queries/export/data?format=` | Export query history as `json`, `csv`, or `pdf` |
| `GET /forecast/{location_id}?days=` | Model-based forecast for an already-resolved location |
| `GET /anomaly-check/{location_id}` | Compare current conditions against this location's historical baseline |
| `GET /enrich/{location_id}` | Country facts (Rest Countries), YouTube videos, and a Maps embed URL for a location |
| `GET /about` | Platform info, PM Accelerator mission, candidate/repo links |

## Tech stack

Python 3.12, FastAPI 0.115, SQLAlchemy 2.0, Pydantic 2.9, PostgreSQL 16, Alembic, Docker Compose, scikit-learn (forecasting model), ReportLab (PDF export). Third-party APIs: OpenWeatherMap (current conditions, forecast, geocoding, air quality), YouTube Data API v3, Google Maps, Rest Countries (no key required).

## Known limitations

The forecasting model uses only geography and seasonality as features (no wind, pressure, or humidity), so it's a climatological estimator rather than a short-horizon meteorological one — it's complementary to, not a replacement for, the live OpenWeatherMap forecast also exposed via `/weather/forecast`. `/enrich/{location_id}` returns partial results (omitting whichever section's API key is missing) rather than failing outright if `YOUTUBE_API_KEY` or `GOOGLE_MAPS_API_KEY` isn't configured.
