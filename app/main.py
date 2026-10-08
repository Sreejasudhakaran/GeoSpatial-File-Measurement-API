"""
FastAPI application entry-point.

Only wiring lives here — no business logic.
Routers will be included as we build each layer.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from app.db.session import create_tables


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle handler."""
    create_tables()
    yield


app = FastAPI(
    title="Geospatial File Measurement API",
    description=(
        "Upload geospatial files (Shapefile .zip or .kml), "
        "extract features, and compute measurements "
        "(area for polygons, length for lines)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Smoke-test endpoint — confirms the server is running."""
    return {"status": "ok"}
