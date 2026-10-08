"""
Tests for app/db/models.py and app/db/session.py.

Uses an isolated in-memory SQLite database to verify:
- Table creation and schema definitions
- Inserting UploadedFile with related Feature rows
- Querying back relationships and JSON properties
- UniqueConstraint enforcement on (file_id, feature_index)
- ON DELETE CASCADE behavior deleting child features when parent file is deleted
- get_db() session generator lifecycle
"""

import json
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Feature, UploadedFile
from app.db.session import get_db


@pytest.fixture
def test_db_session() -> Generator[Session, None, None]:
    """Provide an isolated in-memory SQLite database session with foreign keys enabled."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    # Enable SQLite foreign key constraint enforcement
    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
        cursor = getattr(dbapi_connection, "cursor")()
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


def test_insert_and_query_file_with_features(test_db_session: Session) -> None:
    """Insert an UploadedFile with 2 features and query back relationships and attributes."""
    file_record = UploadedFile(
        filename="parcels.zip",
        file_type="shapefile",
        status="COMPLETED",
        crs="EPSG:4326",
        feature_count=2,
    )
    test_db_session.add(file_record)
    test_db_session.flush()  # Populates file_record.id

    feat1 = Feature(
        file_id=file_record.id,
        feature_index=0,
        geometry_type="Polygon",
        geometry=json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}),
        crs="EPSG:4326",
        properties={"parcel_id": 101, "zone": "commercial"},
        measurement_status="OK",
        area_m2=12345.67,
        length_m=None,
        projected_crs="EPSG:32644",
        warning=None,
    )
    feat2 = Feature(
        file_id=file_record.id,
        feature_index=1,
        geometry_type="LineString",
        geometry=json.dumps({"type": "LineString", "coordinates": [[0, 0], [1, 1]]}),
        crs="EPSG:4326",
        properties={"road_id": 202, "lanes": 4},
        measurement_status="OK",
        area_m2=None,
        length_m=1106.75,
        projected_crs="EPSG:32644",
        warning=None,
    )
    test_db_session.add_all([feat1, feat2])
    test_db_session.commit()

    # Query back
    stmt = select(UploadedFile).where(UploadedFile.id == file_record.id)
    fetched_file = test_db_session.scalars(stmt).one()

    assert fetched_file.filename == "parcels.zip"
    assert fetched_file.feature_count == 2
    assert len(fetched_file.features) == 2

    # Verify features and JSON properties
    f0 = fetched_file.features[0]
    assert f0.feature_index == 0
    assert f0.geometry_type == "Polygon"
    assert f0.properties["parcel_id"] == 101
    assert f0.area_m2 == 12345.67

    f1 = fetched_file.features[1]
    assert f1.feature_index == 1
    assert f1.length_m == 1106.75


def test_unique_constraint_file_id_and_feature_index(test_db_session: Session) -> None:
    """Attempting to insert two features with the same (file_id, feature_index) must fail."""
    file_record = UploadedFile(
        filename="test.kml",
        file_type="kml",
        status="COMPLETED",
        feature_count=1,
    )
    test_db_session.add(file_record)
    test_db_session.flush()

    feat_a = Feature(
        file_id=file_record.id,
        feature_index=0,
        geometry_type="Point",
        geometry="{}",
        crs="EPSG:4326",
        properties={},
        measurement_status="NOT_REQUIRED",
    )
    feat_duplicate = Feature(
        file_id=file_record.id,
        feature_index=0,  # Duplicate index for the same file_id
        geometry_type="Point",
        geometry="{}",
        crs="EPSG:4326",
        properties={},
        measurement_status="NOT_REQUIRED",
    )

    test_db_session.add(feat_a)
    test_db_session.commit()

    test_db_session.add(feat_duplicate)
    with pytest.raises(IntegrityError):
        test_db_session.commit()

    test_db_session.rollback()


def test_cascade_delete_removes_child_features(test_db_session: Session) -> None:
    """Deleting an UploadedFile must cascade and delete all associated Feature records."""
    file_record = UploadedFile(
        filename="cascade_test.zip",
        file_type="shapefile",
        status="COMPLETED",
        feature_count=2,
    )
    test_db_session.add(file_record)
    test_db_session.flush()

    file_id = file_record.id
    feat1 = Feature(
        file_id=file_id,
        feature_index=0,
        geometry_type="Point",
        geometry="{}",
        crs="EPSG:4326",
        properties={},
        measurement_status="NOT_REQUIRED",
    )
    feat2 = Feature(
        file_id=file_id,
        feature_index=1,
        geometry_type="Point",
        geometry="{}",
        crs="EPSG:4326",
        properties={},
        measurement_status="NOT_REQUIRED",
    )
    test_db_session.add_all([feat1, feat2])
    test_db_session.commit()

    # Confirm 2 features exist
    features_before = test_db_session.scalars(select(Feature).where(Feature.file_id == file_id)).all()
    assert len(features_before) == 2

    # Delete the parent UploadedFile
    test_db_session.delete(file_record)
    test_db_session.commit()

    # Verify both parent and child features are gone
    file_after = test_db_session.scalars(select(UploadedFile).where(UploadedFile.id == file_id)).first()
    assert file_after is None

    features_after = test_db_session.scalars(select(Feature).where(Feature.file_id == file_id)).all()
    assert len(features_after) == 0


def test_get_db_dependency_lifecycle() -> None:
    """Verify get_db yields an active session and closes it cleanly."""
    gen = get_db()
    session = next(gen)

    assert isinstance(session, Session)
    assert session.is_active

    # Closing generator should trigger the finally block in get_db
    with pytest.raises(StopIteration):
        next(gen)
