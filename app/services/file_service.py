"""
File processing and measurement orchestration service.

SERVICE LAYER RESPONSIBILITIES:
- Owns database transactions (commits and rollbacks).
- Orchestrates file validation, disk persistence, geo extraction, and measurement calculation.
- Guarantees rows never remain stuck in 'PROCESSING' state.
- Translates domain/reader results into persisted database records.
"""

import json
import logging
from pathlib import Path
import shutil
from typing import Any
import uuid

import shapely.geometry
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import (
    FileTooLargeError,
    InvalidFileError,
    NotFoundError,
    UnsupportedFileTypeError,
)
from app.db.models import Feature, UploadedFile
from app.geo.measurements import measure
from app.geo.models import (
    STATUS_ERROR,
    Measurement,
)
from app.geo.readers import find_shapefile, read_features, safe_extract_zip

logger = logging.getLogger(__name__)


def process_upload(
    db: Session,
    filename: str,
    content: bytes,
    storage_dir: Path | None = None,
) -> UploadedFile:
    """Validate, persist, parse, and measure an uploaded geospatial file.

    Workflow:
    1. Validate extension (.zip, .kml) and size (<= MAX_UPLOAD_MB). Empty content is rejected.
    2. Insert an UploadedFile row in PROCESSING state and commit immediately.
    3. Save raw file to STORAGE_DIR/{file_id}/. For zips, verify extraction and presence of .shp.
       If corrupted or missing .shp, delete the row and files, and raise InvalidFileError.
    4. Call readers.read_features. Compute measure() per feature with isolated error handling.
    5. Bulk insert Feature rows; update file metadata (CRS, count, COMPLETED) and commit.
    6. For missing .prj or 0 features, keep the row, set status FAILED with error message.
    7. On any unhandled exception, set status FAILED, log traceback, and never leave row stuck.

    Args:
        db: Active SQLAlchemy database session.
        filename: Name of the uploaded file.
        content: Raw file content bytes.
        storage_dir: Optional base directory override (useful for isolated tests).

    Returns:
        The updated UploadedFile instance.

    Raises:
        UnsupportedFileTypeError: If file is not .zip or .kml.
        FileTooLargeError: If content exceeds MAX_UPLOAD_MB.
        InvalidFileError: If file is empty, corrupted zip, or contains no .shp.
    """
    # 1. Preliminary validation
    suffix = Path(filename).suffix.lower()
    if suffix not in (".zip", ".kml"):
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{suffix}'. Only .zip (Shapefile) and .kml are supported."
        )

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise FileTooLargeError(
            f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_MB} MB."
        )

    if len(content) == 0:
        raise InvalidFileError("Uploaded file is empty.")

    # 2. Create initial database record in PROCESSING state
    file_type = "shapefile" if suffix == ".zip" else "kml"
    file_id = str(uuid.uuid4())
    uploaded_file = UploadedFile(
        id=file_id,
        filename=filename,
        file_type=file_type,
        status="PROCESSING",
        feature_count=0,
    )
    db.add(uploaded_file)
    db.commit()
    db.refresh(uploaded_file)

    # 3. Save upload to disk
    base_storage = storage_dir or settings.STORAGE_DIR
    file_dir = base_storage / file_id
    file_dir.mkdir(parents=True, exist_ok=True)
    saved_file_path = file_dir / filename
    saved_file_path.write_bytes(content)

    # For .zip files, test extraction and verify .shp exists
    if suffix == ".zip":
        try:
            safe_extract_zip(saved_file_path, file_dir)
            find_shapefile(file_dir)
        except InvalidFileError:
            # Clean up both DB row and folder, then propagate InvalidFileError (HTTP 400)
            db.delete(uploaded_file)
            db.commit()
            shutil.rmtree(file_dir, ignore_errors=True)
            raise

    # 4 & 5 & 6. Read features and compute measurements
    try:
        try:
            features = read_features(saved_file_path)
        except InvalidFileError as exc:
            # E.g. Missing .prj: keep DB row, mark status FAILED with message
            uploaded_file.status = "FAILED"
            uploaded_file.error_message = str(exc)
            db.commit()
            db.refresh(uploaded_file)
            return uploaded_file

        if not features:
            uploaded_file.status = "FAILED"
            uploaded_file.error_message = "File contains zero readable features."
            db.commit()
            db.refresh(uploaded_file)
            return uploaded_file

        feature_models: list[Feature] = []
        for feat in features:
            # Compute measurement with individual isolation
            try:
                meas = measure(feat.geometry, feat.source_crs)
            except Exception as m_exc:
                meas = Measurement(
                    status=STATUS_ERROR,
                    area_m2=None,
                    length_m=None,
                    projected_crs=None,
                    warning=f"measurement failed: {str(m_exc)}",
                )

            # Serialize geometry to GeoJSON
            if feat.geometry is not None and not feat.geometry.is_empty:
                geom_json = json.dumps(shapely.geometry.mapping(feat.geometry))
                geom_type = feat.geometry.geom_type
            else:
                geom_json = json.dumps(None)
                geom_type = "Unknown"

            feature_models.append(
                Feature(
                    file_id=uploaded_file.id,
                    feature_index=feat.index,
                    geometry_type=geom_type,
                    geometry=geom_json,
                    crs=feat.source_crs,
                    properties=feat.properties,
                    measurement_status=meas.status,
                    area_m2=meas.area_m2,
                    length_m=meas.length_m,
                    projected_crs=meas.projected_crs,
                    warning=meas.warning,
                )
            )

        # Bulk insert child features and finalize file status
        db.add_all(feature_models)
        uploaded_file.crs = features[0].source_crs
        uploaded_file.feature_count = len(features)
        uploaded_file.status = "COMPLETED"
        uploaded_file.error_message = None
        db.commit()
        db.refresh(uploaded_file)
        return uploaded_file

    except Exception as exc:
        # 7. Unhandled exception fallback
        logger.exception("Unexpected error processing file %s (%s)", filename, uploaded_file.id)
        uploaded_file.status = "FAILED"
        uploaded_file.error_message = f"Processing error: {str(exc)}"
        db.commit()
        db.refresh(uploaded_file)
        return uploaded_file


def get_file(db: Session, file_id: str) -> UploadedFile:
    """Retrieve an UploadedFile by ID or raise NotFoundError."""
    stmt = select(UploadedFile).where(UploadedFile.id == file_id)
    file_record = db.scalars(stmt).first()
    if not file_record:
        raise NotFoundError(f"File with id '{file_id}' not found.")
    return file_record


def get_measurements(
    db: Session,
    file_id: str,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Feature], int]:
    """Retrieve paginated feature measurements for an UploadedFile.

    Args:
        db: Active SQLAlchemy database session.
        file_id: UploadedFile UUID string.
        limit: Max number of records to return.
        offset: Number of records to skip.

    Returns:
        A tuple of (items, total_count).

    Raises:
        NotFoundError: If the parent file does not exist.
    """
    # Ensure parent file exists first
    get_file(db, file_id)

    # Compute total count
    count_stmt = select(func.count(Feature.id)).where(Feature.file_id == file_id)
    total = db.scalar(count_stmt) or 0

    # Query paginated features ordered by feature_index
    stmt = (
        select(Feature)
        .where(Feature.file_id == file_id)
        .order_by(Feature.feature_index)
        .limit(limit)
        .offset(offset)
    )
    items = list(db.scalars(stmt).all())

    return items, total
