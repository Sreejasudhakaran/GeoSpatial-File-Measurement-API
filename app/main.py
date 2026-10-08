"""
FastAPI application entry-point.

Only wiring lives here — no business logic.
Registers routers, startup lifespans, and global exception handlers.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.files import router as files_router
from app.core.errors import (
    FileTooLargeError,
    InvalidFileError,
    NotFoundError,
    UnsupportedFileTypeError,
)
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

# ---------------------------------------------------------------------------
# Global Exception Handlers: Map pure domain exceptions to standard HTTP codes
# ---------------------------------------------------------------------------


@app.exception_handler(UnsupportedFileTypeError)
async def unsupported_file_type_handler(
    request: Request, exc: UnsupportedFileTypeError
) -> JSONResponse:
    """Map UnsupportedFileTypeError to 415 Unsupported Media Type."""
    return JSONResponse(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        content={"detail": exc.message},
    )


@app.exception_handler(FileTooLargeError)
async def file_too_large_handler(
    request: Request, exc: FileTooLargeError
) -> JSONResponse:
    """Map FileTooLargeError to 413 Payload Too Large."""
    return JSONResponse(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        content={"detail": exc.message},
    )


@app.exception_handler(InvalidFileError)
async def invalid_file_handler(
    request: Request, exc: InvalidFileError
) -> JSONResponse:
    """Map InvalidFileError to 400 Bad Request."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.message},
    )


@app.exception_handler(NotFoundError)
async def not_found_handler(
    request: Request, exc: NotFoundError
) -> JSONResponse:
    """Map NotFoundError to 404 Not Found."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": exc.message},
    )


# ---------------------------------------------------------------------------
# Routers and Health Endpoint
# ---------------------------------------------------------------------------

app.include_router(files_router)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Smoke-test endpoint — confirms the server is running."""
    return {"status": "ok"}
