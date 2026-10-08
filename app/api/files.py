"""
HTTP API router for file uploads, metadata inspection, and measurements.

THIN CONTROLLER LAYER:
- Reads HTTP parameters and headers.
- Injects database session via get_db dependency.
- Delegates business logic to app.services.file_service.
- Returns strongly-typed Pydantic response models.
- Domain exceptions are mapped by global exception handlers in app.main.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.files import FileResponse, MeasurementsResponse
from app.services.file_service import get_file, get_measurements, process_upload

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=FileResponse,
    summary="Upload and process geospatial file",
    description="Accepts a Shapefile (.zip) or KML (.kml) file, extracts features, and computes measurements.",
)
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=FileResponse,
    include_in_schema=False,
)
async def upload_file(
    file: Annotated[UploadFile, File(description="Geospatial file (.zip Shapefile archive or .kml)")],
    db: Session = Depends(get_db),
) -> FileResponse:
    """Handle multipart file upload, persist, and execute synchronous feature measurement."""
    content: bytes = await file.read()
    filename: str = file.filename or "unknown"

    uploaded_record = process_upload(
        db=db,
        filename=filename,
        content=content,
    )
    return uploaded_record  # Pydantic parses directly from SQLAlchemy model via from_attributes=True


@router.get(
    "/{id}/",
    response_model=FileResponse,
    summary="Get uploaded file metadata and status",
)
@router.get(
    "/{id}",
    response_model=FileResponse,
    include_in_schema=False,
)
def get_file_info(
    id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Retrieve metadata, feature count, and processing status for an uploaded file."""
    return get_file(db=db, file_id=id)


@router.get(
    "/{id}/measurements/",
    response_model=MeasurementsResponse,
    summary="Get computed feature measurements",
)
@router.get(
    "/{id}/measurements",
    response_model=MeasurementsResponse,
    include_in_schema=False,
)
def get_file_measurements(
    id: str,
    limit: Annotated[int, Query(ge=1, le=1000, description="Max records to return")] = 100,
    offset: Annotated[int, Query(ge=0, description="Records to skip")] = 0,
    db: Session = Depends(get_db),
) -> MeasurementsResponse:
    """Retrieve paginated feature geometries, attributes, and planar measurements."""
    items, total = get_measurements(
        db=db,
        file_id=id,
        limit=limit,
        offset=offset,
    )
    return MeasurementsResponse(
        file_id=id,
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )
