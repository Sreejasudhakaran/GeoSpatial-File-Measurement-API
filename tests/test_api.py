"""
End-to-end integration tests for HTTP API endpoints.

Verifies:
- POST /api/files/ with Shapefile archive (.zip) and KML (.kml)
- GET /api/files/{id}/ metadata retrieval
- GET /api/files/{id}/measurements/ with real metric area validation (within 1% of 1 km²)
- mixed.kml geometry status handling (Point: NOT_REQUIRED, Line: length, Polygon: area)
- Pagination (limit & offset)
- 404 Not Found for non-existent file IDs
- 415 Unsupported Media Type for invalid extensions (.txt)
- 400 Bad Request for corrupted archives
- Missing .prj archive returns 201 with FAILED status
- Trailing slash flexibility (endpoints work both with and without trailing slash)
"""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.models import Base
from app.db.session import get_db
from app.main import app

SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"


@pytest.fixture
def api_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    """TestClient fixture overriding DB session and storage directory."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    original_storage = settings.STORAGE_DIR
    settings.STORAGE_DIR = tmp_path

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    settings.STORAGE_DIR = original_storage
    Base.metadata.drop_all(bind=test_engine)


def test_upload_shapefile_zip_and_measure_1km_square(api_client: TestClient) -> None:
    """Upload polygons.zip, check metadata, and verify measured area of 1km square."""
    zip_bytes = (SAMPLE_DATA_DIR / "polygons.zip").read_bytes()

    # 1. POST /api/files/
    resp_upload = api_client.post(
        "/api/files/",
        files={"file": ("polygons.zip", zip_bytes, "application/zip")},
    )
    assert resp_upload.status_code == 201
    file_data = resp_upload.json()

    file_id = file_data["id"]
    assert file_data["filename"] == "polygons.zip"
    assert file_data["status"] == "COMPLETED"
    assert file_data["feature_count"] == 2
    assert "4326" in file_data["crs"]
    assert file_data["error_message"] is None

    # 2. GET /api/files/{id}/
    resp_info = api_client.get(f"/api/files/{file_id}/")
    assert resp_info.status_code == 200
    assert resp_info.json()["id"] == file_id
    assert resp_info.json()["status"] == "COMPLETED"

    # 3. GET /api/files/{id}/measurements/
    resp_meas = api_client.get(f"/api/files/{file_id}/measurements/")
    assert resp_meas.status_code == 200
    meas_data = resp_meas.json()

    assert meas_data["file_id"] == file_id
    assert meas_data["total"] == 2
    assert len(meas_data["items"]) == 2

    # Feature 0: 1 km square near Hyderabad (nominal 1,000,000 m²)
    f0 = meas_data["items"][0]
    assert f0["feature_index"] == 0
    assert f0["geometry_type"] == "Polygon"
    assert isinstance(f0["geometry"], dict)  # GeoJSON parsed as dict
    assert f0["geometry"]["type"] == "Polygon"
    assert f0["measurement_status"] == "OK"
    assert f0["length_m"] is None

    # Verify area is within 1% of 1 km² (1,000,000 m²)
    assert f0["area_m2"] == pytest.approx(1_000_000.0, rel=0.01)

    # Feature 1: holed polygon
    f1 = meas_data["items"][1]
    assert f1["feature_index"] == 1
    assert f1["area_m2"] is not None and f1["area_m2"] > 0


def test_mixed_kml_geometry_statuses(api_client: TestClient) -> None:
    """Upload mixed.kml and verify Point (NOT_REQUIRED), Line (length), and Polygon (area)."""
    kml_bytes = (SAMPLE_DATA_DIR / "mixed.kml").read_bytes()

    resp_upload = api_client.post(
        "/api/files/",
        files={"file": ("mixed.kml", kml_bytes, "application/vnd.google-earth.kml+xml")},
    )
    assert resp_upload.status_code == 201
    file_id = resp_upload.json()["id"]

    resp_meas = api_client.get(f"/api/files/{file_id}/measurements/")
    assert resp_meas.status_code == 200
    items = resp_meas.json()["items"]
    assert len(items) == 3

    # Point: status NOT_REQUIRED, area=None, length=None
    assert items[0]["geometry_type"] == "Point"
    assert items[0]["measurement_status"] == "NOT_REQUIRED"
    assert items[0]["area_m2"] is None
    assert items[0]["length_m"] is None

    # LineString: status OK, length > 0, area=None
    assert items[1]["geometry_type"] == "LineString"
    assert items[1]["measurement_status"] == "OK"
    assert items[1]["length_m"] is not None and items[1]["length_m"] > 0
    assert items[1]["area_m2"] is None

    # Polygon: status OK, area > 0, length=None
    assert items[2]["geometry_type"] == "Polygon"
    assert items[2]["measurement_status"] == "OK"
    assert items[2]["area_m2"] is not None and items[2]["area_m2"] > 0
    assert items[2]["length_m"] is None


def test_measurements_pagination(api_client: TestClient) -> None:
    """Verify limit and offset query parameters on GET measurements."""
    kml_bytes = (SAMPLE_DATA_DIR / "mixed.kml").read_bytes()
    resp_upload = api_client.post(
        "/api/files/",
        files={"file": ("mixed.kml", kml_bytes, "application/vnd.google-earth.kml+xml")},
    )
    file_id = resp_upload.json()["id"]

    # Request second feature only
    resp = api_client.get(f"/api/files/{file_id}/measurements/?limit=1&offset=1")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 3
    assert data["limit"] == 1
    assert data["offset"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["feature_index"] == 1


def test_unknown_file_id_returns_404(api_client: TestClient) -> None:
    """Querying an unknown file ID returns HTTP 404 with detail message."""
    unknown_id = "00000000-0000-0000-0000-000000000000"

    resp_info = api_client.get(f"/api/files/{unknown_id}/")
    assert resp_info.status_code == 404
    assert "not found" in resp_info.json()["detail"].lower()

    resp_meas = api_client.get(f"/api/files/{unknown_id}/measurements/")
    assert resp_meas.status_code == 404
    assert "not found" in resp_meas.json()["detail"].lower()


def test_unsupported_file_extension_returns_415(api_client: TestClient) -> None:
    """Uploading unhandled file types (.txt, .geojson) returns HTTP 415."""
    resp = api_client.post(
        "/api/files/",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )
    assert resp.status_code == 415
    assert "unsupported file type" in resp.json()["detail"].lower()


def test_corrupted_zip_returns_400(api_client: TestClient) -> None:
    """Uploading a corrupted zip file returns HTTP 400 Bad Request."""
    corrupt_bytes = (SAMPLE_DATA_DIR / "corrupt.zip").read_bytes()

    resp = api_client.post(
        "/api/files/",
        files={"file": ("corrupt.zip", corrupt_bytes, "application/zip")},
    )
    assert resp.status_code == 400
    assert "corrupt" in resp.json()["detail"].lower() or "zip" in resp.json()["detail"].lower()


def test_no_prj_shapefile_returns_201_with_failed_status(api_client: TestClient) -> None:
    """Shapefile without .prj cannot be measured; returns HTTP 201 with status FAILED."""
    no_prj_bytes = (SAMPLE_DATA_DIR / "no_prj.zip").read_bytes()

    resp = api_client.post(
        "/api/files/",
        files={"file": ("no_prj.zip", no_prj_bytes, "application/zip")},
    )
    assert resp.status_code == 201
    data = resp.json()

    assert data["status"] == "FAILED"
    assert data["error_message"] is not None
    assert "missing .prj" in data["error_message"].lower()

    # GET /api/files/{id}/ confirms FAILED status and error_message
    file_id = data["id"]
    resp_get = api_client.get(f"/api/files/{file_id}/")
    assert resp_get.status_code == 200
    assert resp_get.json()["status"] == "FAILED"
    assert "missing .prj" in resp_get.json()["error_message"].lower()


def test_trailing_slash_handling(api_client: TestClient) -> None:
    """Verify endpoints function identically both with and without trailing slash."""
    kml_bytes = (SAMPLE_DATA_DIR / "polygons.kml").read_bytes()

    # POST without trailing slash: /api/files
    resp_upload = api_client.post(
        "/api/files",
        files={"file": ("polygons.kml", kml_bytes, "application/vnd.google-earth.kml+xml")},
    )
    assert resp_upload.status_code == 201
    file_id = resp_upload.json()["id"]

    # GET info without trailing slash: /api/files/{id}
    resp_info = api_client.get(f"/api/files/{file_id}")
    assert resp_info.status_code == 200
    assert resp_info.json()["id"] == file_id

    # GET measurements without trailing slash: /api/files/{id}/measurements
    resp_meas = api_client.get(f"/api/files/{file_id}/measurements")
    assert resp_meas.status_code == 200
    assert len(resp_meas.json()["items"]) == 2
