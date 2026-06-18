"""Atlas Weather Intelligence Platform — FastAPI application entrypoint."""
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.routers import (
    about_router, anomaly_router, enrich_router,
    forecast_router, location_router, query_router, weather_router,
)

app = FastAPI(
    title="Atlas Weather Intelligence Platform",
    description=(
        "A weather platform combining live conditions with a forecasting model "
        "trained on the Global Weather Repository dataset. "
        "Built for the PM Accelerator AI Engineer Internship — Dual Role submission."
    ),
    version="1.0.0",
)

app.include_router(weather_router)
app.include_router(location_router)
app.include_router(query_router)
app.include_router(forecast_router)
app.include_router(anomaly_router)
app.include_router(enrich_router)
app.include_router(about_router)


@app.get("/health", tags=["system"])
def health_check(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
