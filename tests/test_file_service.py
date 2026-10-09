"""
Tests for app/services/file_service.py.

Verifies:
- Happy path for Shapefile archive (polygons.zip)
- Happy path for KML (polygons.kml)
- mixed.kml features receive correct measurement statuses (Point: NOT_REQUIRED, Line: OK, Poly: OK)
- no_prj.zip transitions to FAILED status with error_message retained in DB
- corrupt.zip raises InvalidFileError and leaves no leftover DB row or directory
- Wrong file extension raises UnsupportedFileTypeError
- Oversized upload raises FileTooLargeError
- Empty file content raises InvalidFileError
- get_file and get_measurements handle pagination and NotFoundError
"""

from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.errors import (
    FileTooLargeError,
    InvalidFileError,
    NotFoundError,
    UnsupportedFileTypeError,
)
from app.db.models import Base, UploadedFile
from app.services.file_service import get_file, get_measurements, process_upload

SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide an isolated in-memory SQLite database session with foreign keys enabled."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


def test_happy_path_shapefile_zip(db_session: Session, tmp_path: Path) -> None:
    """Upload and process polygons.zip successfully."""
    content = (SAMPLE_DATA_DIR / "polygons.zip").read_bytes()

    result = process_upload(db_session, "polygons.zip", content, storage_dir=tmp_path)

    assert result.status == "COMPLETED"
    assert result.file_type == "shapefile"
    assert result.feature_count == 2
    assert "4326" in str(result.crs)
    assert result.error_message is None

    # Query back measurements
    items, total = get_measurements(db_session, result.id)
    assert total == 2
    assert len(items) == 2

    # Both are polygons with area > 0
    for feat in items:
        assert feat.geometry_type == "Polygon"
        assert feat.measurement_status == "OK"
        assert feat.area_m2 is not None and feat.area_m2 > 0
        assert feat.length_m is None
        assert feat.projected_crs is not None


def test_happy_path_kml(db_session: Session, tmp_path: Path) -> None:
    """Upload and process polygons.kml successfully."""
    content = (SAMPLE_DATA_DIR / "polygons.kml").read_bytes()

    result = process_upload(db_session, "polygons.kml", content, storage_dir=tmp_path)

    assert result.status == "COMPLETED"
    assert result.file_type == "kml"
    assert result.feature_count == 2
    assert result.crs == "EPSG:4326"
    assert result.error_message is None


def test_mixed_kml_correct_measurement_statuses(db_session: Session, tmp_path: Path) -> None:
    """mixed.kml must assign Point -> NOT_REQUIRED, Line -> OK, Polygon -> OK."""
    content = (SAMPLE_DATA_DIR / "mixed.kml").read_bytes()

    result = process_upload(db_session, "mixed.kml", content, storage_dir=tmp_path)

    assert result.status == "COMPLETED"
    assert result.feature_count == 3

    items, total = get_measurements(db_session, result.id)
    assert total == 3

    # Feature 0: Point
    f_pt = items[0]
    assert f_pt.geometry_type == "Point"
    assert f_pt.measurement_status == "NOT_REQUIRED"
    assert f_pt.area_m2 is None
    assert f_pt.length_m is None

    # Feature 1: LineString
    f_line = items[1]
    assert f_line.geometry_type == "LineString"
    assert f_line.measurement_status == "OK"
    assert f_line.length_m is not None and f_line.length_m > 0
    assert f_line.area_m2 is None

    # Feature 2: Polygon
    f_poly = items[2]
    assert f_poly.geometry_type == "Polygon"
    assert f_poly.measurement_status == "OK"
    assert f_poly.area_m2 is not None and f_poly.area_m2 > 0
    assert f_poly.length_m is None


def test_no_prj_shapefile_transitions_to_failed(db_session: Session, tmp_path: Path) -> None:
    """Missing .prj must keep the DB row, set status FAILED, and store error message."""
    content = (SAMPLE_DATA_DIR / "no_prj.zip").read_bytes()

    result = process_upload(db_session, "no_prj.zip", content, storage_dir=tmp_path)

    assert result.status == "FAILED"
    assert result.error_message is not None
    assert "missing .prj" in result.error_message.lower()

    # Verify the row remains queryable in the DB
    fetched = get_file(db_session, result.id)
    assert fetched.id == result.id
    assert fetched.status == "FAILED"


def test_corrupt_zip_raises_and_leaves_no_leftover_row(db_session: Session, tmp_path: Path) -> None:
    """Corrupt zip must raise InvalidFileError and delete both DB row and folder."""
    content = (SAMPLE_DATA_DIR / "corrupt.zip").read_bytes()

    with pytest.raises(InvalidFileError):
        process_upload(db_session, "corrupt.zip", content, storage_dir=tmp_path)

    # Database must contain 0 uploaded_files
    all_files = db_session.scalars(select(UploadedFile)).all()
    assert len(all_files) == 0

    # Storage dir must have no leftover subdirectories
    subdirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(subdirs) == 0


def test_unsupported_file_extension(db_session: Session) -> None:
    """Uploading .geojson or other unhandled formats raises UnsupportedFileTypeError."""
    with pytest.raises(UnsupportedFileTypeError) as exc_info:
        process_upload(db_session, "data.csv", b"col1,col2\n1,2")

    assert "unsupported file type" in str(exc_info.value).lower()


def test_oversized_file(db_session: Session) -> None:
    """Uploading content exceeding MAX_UPLOAD_MB raises FileTooLargeError."""
    # Simulate a file 1 byte larger than allowed limit
    limit_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    oversized_content = b"X" * (limit_bytes + 1)

    with pytest.raises(FileTooLargeError) as exc_info:
        process_upload(db_session, "big.zip", oversized_content)

    assert "size" in str(exc_info.value).lower()


def test_empty_file_content(db_session: Session) -> None:
    """Uploading 0-byte content raises InvalidFileError."""
    with pytest.raises(InvalidFileError) as exc_info:
        process_upload(db_session, "empty.kml", b"")

    assert "empty" in str(exc_info.value).lower()


def test_get_file_and_get_measurements_pagination(db_session: Session, tmp_path: Path) -> None:
    """Verify get_file and get_measurements pagination and NotFoundError handling."""
    content = (SAMPLE_DATA_DIR / "mixed.kml").read_bytes()
    file_record = process_upload(db_session, "mixed.kml", content, storage_dir=tmp_path)

    # get_file happy path
    fetched = get_file(db_session, file_record.id)
    assert fetched.id == file_record.id

    # Pagination: limit=1, offset=1 returns the second feature
    items_paged, total = get_measurements(db_session, file_record.id, limit=1, offset=1)
    assert total == 3
    assert len(items_paged) == 1
    assert items_paged[0].feature_index == 1

    # Unknown ID raises NotFoundError
    with pytest.raises(NotFoundError):
        get_file(db_session, "non-existent-uuid")

    with pytest.raises(NotFoundError):
        get_measurements(db_session, "non-existent-uuid")
