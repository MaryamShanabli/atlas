# Atlas Weather Intelligence Platform

> *A weather platform that doesn't just report conditions — it tells you whether they're unusual, predicts what's coming, and explains the place you're looking at.*

Built for the **PM Accelerator AI Engineer Internship — Dual Role Submission (Backend + Data Science)**.

---

## PM Accelerator Mission

> PM Accelerator is the world's most accessible product management program, providing aspiring and experienced PMs with the skills, mentorship, and real-world experience needed to land and excel in product management roles.

---

## What Atlas does

| Feature | Detail |
|---|---|
| Live weather | Current conditions for any city, zip code, landmark, or coordinates |
| Geocoding-first resolution | Ambiguous input ("Springfield") is resolved to a canonical lat/long before any query |
| ML-powered forecast | 7–14 day temperature forecast from a Gradient Boosting model trained on 147,930 rows of global data |
| Anomaly detection | Flags if current conditions are statistically unusual for that specific location |
| Air quality | Live AQI + PM2.5 alongside every weather reading |
| Full CRUD | Create, read, update, delete stored weather queries with date-range validation |
| Export | JSON, CSV, and PDF export of stored records |
| Enrichment | YouTube videos + Google Maps embed + Rest Countries context for any location |
| Swagger UI | Full interactive API at `/docs` — no frontend needed to explore |

---

## Architecture

```
Client / user
      │
      ▼
FastAPI application (port 8000)
  ├── /weather     — live conditions + forecast
  ├── /locations   — geocoding + location registry
  ├── /queries     — CRUD + export
  ├── /forecast    — ML model direct
  ├── /anomaly-check
  ├── /enrich      — YouTube + Maps + Rest Countries
  ├── /about       — platform info
  └── /health      — liveness + DB check
      │
      ├── OpenWeatherMap API (live weather + geocoding + air quality)
      ├── PostgreSQL (locations, weather_queries, forecast_cache)
      └── ML layer (forecast_model.joblib — loaded once at startup)
            │
            └── Trained offline in notebooks/01_atlas_notebook.ipynb
                on the Global Weather Repository (Kaggle, 147,930 rows)
```

The model artifacts are the literal link between the data science notebook and the live API. Deleting either half breaks the other — this is one system, not two assessments.

---

## Quick start

### Prerequisites
- Docker Desktop

### 1. Clone and configure
```bash
git clone https://github.com/MaryamShanabli/atlas.git
cd atlas
cp .env.example .env
# Fill in OPENWEATHERMAP_API_KEY (and optionally YOUTUBE_API_KEY, GOOGLE_MAPS_API_KEY)
```

### 2. Start the platform
```bash
docker-compose up -d
docker-compose exec api alembic upgrade head
```

### 3. Explore the API
Open **http://localhost:8000/docs** — full interactive Swagger UI.

### 4. Test a live call
```bash
curl "http://localhost:8000/weather/current?location=London"
```

---

## API reference summary

| Method | Endpoint | Description |
|---|---|---|
| GET | `/weather/current?location=` | Live weather for any location |
| GET | `/weather/forecast?location=` | 7-day ML + live forecast |
| POST | `/locations/resolve` | Geocode raw input to canonical location |
| GET | `/locations` | List all stored locations |
| POST | `/queries` | CREATE: store weather query for date range |
| GET | `/queries` | READ: list stored queries (filterable) |
| GET | `/queries/{id}` | READ: single query detail |
| PUT | `/queries/{id}` | UPDATE: modify a stored query |
| DELETE | `/queries/{id}` | DELETE: remove a query |
| GET | `/queries/export/data?format=json\|csv\|pdf` | Export stored records |
| GET | `/forecast/{location_id}` | ML model forecast direct |
| GET | `/anomaly-check/{location_id}` | Is current reading unusual? |
| GET | `/enrich/{location_id}` | YouTube + Maps + country info |
| GET | `/health` | Liveness + DB connectivity |
| GET | `/about` | Platform + PM Accelerator info |

Full request/response schemas are in Swagger UI at `/docs`.

---

## Data Science methodology

**Dataset:** [Global Weather Repository](https://www.kaggle.com/datasets/nelgiriyewithana/global-weather-repository) — 147,930 rows × 41 columns, 268 cities, 2024-05-16 to 2026-06-17.

**Cleaning decisions (not boilerplate):**
- Zero missing values found — cleaning effort focused on two real problems
- Physically impossible readings (79°C temperature, 2963 km/h wind) flagged via physical-limit thresholds, not statistical z-scores (avoids incorrectly flagging genuine extreme-but-real events)
- Country name contamination (same city logged as "Südkorea" and "South Korea") fixed via coordinate clustering — rows within 0.01° of each other share a canonical English country label

**Models compared:**
| Model | MAE | RMSE |
|---|---|---|
| Seasonal naive baseline | 4.017°C | 5.231°C |
| Gradient Boosting | 3.765°C | 4.842°C |

6.3% MAE improvement over a strong baseline. Honest finding: seasonal climatology (the baseline) is a genuinely competitive forecaster for global daily temperature, so 6.3% improvement is meaningful rather than inflated.

**Notebook:** `notebooks/01_atlas_notebook.ipynb` — covers cleaning, EDA, anomaly detection, model comparison, feature importance, environmental impact, and geographic patterns. Run it once to regenerate the model artifacts, which are then served live by the API.

---

## Running tests

```bash
# Start the database first
docker-compose up -d db

# Run the full suite
pip install -r requirements-dev.txt
pytest -v
```

CI runs automatically on every push via `.github/workflows/ci.yml`.

---

## Project structure

```
atlas/
├── app/
│   ├── core/          # config, database session
│   ├── ml/            # artifact loader (loaded at startup)
│   ├── models_db/     # SQLAlchemy ORM models
│   ├── repositories/  # database access layer
│   ├── routers/       # HTTP endpoints
│   ├── schemas/       # Pydantic request/response models
│   └── services/      # business logic
├── alembic/           # database migrations
├── models/            # trained .joblib artifacts
├── notebooks/         # DS notebook + supporting modules
├── tests/             # pytest test suite
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## What I'd improve with more time

1. **Prophet model** — add a third model to the comparison using Facebook Prophet, which is purpose-built for this kind of daily seasonal data and would likely outperform the global gradient boosting model for per-city forecasts
2. **Per-city model coverage** — train dedicated models for the highest-traffic cities instead of relying solely on the global model
3. **Caching layer** — add Redis for OpenWeatherMap response caching to handle rate limits gracefully at scale
4. **Authentication** — row-level security wasn't required, but a real deployment would add JWT-based user identity so queries are associated with the person who created them
5. **Interactive map** — replace the Google Maps embed URL with a Plotly/Folium spatial visualization showing all locations, coloured by temperature or AQI

---

## API keys

| Key | Where to get | Required for |
|---|---|---|
| `OPENWEATHERMAP_API_KEY` | https://openweathermap.org/api | Weather, forecast, geocoding, air quality |
| `YOUTUBE_API_KEY` | Google Cloud Console → YouTube Data API v3 | `/enrich` YouTube videos |
| `GOOGLE_MAPS_API_KEY` | Google Cloud Console → Maps Embed API | `/enrich` map embed |
| Rest Countries | No key needed | `/enrich` country info |

---

*Built by Maryam Shanabli — PM Accelerator AI Engineer Internship, Dual Role submission*
