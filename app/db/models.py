"""
SQLAlchemy 2.0 database models.

Follows modern DeclarativeBase, Mapped typing, and mapped_column declarations.
"""

from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base class for all SQLAlchemy models."""
    pass


class UploadedFile(Base):
    """Represents an uploaded geospatial file archive or document.

    Tracks file lifecycle status, metadata, feature count, and processing errors.
    """

    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        doc="UUID string uniquely identifying the uploaded file.",
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Original filename supplied by the user during upload.",
    )
    file_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Detected file format: 'shapefile' or 'kml'.",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PROCESSING",
        doc="Processing status: 'PROCESSING', 'COMPLETED', or 'FAILED'.",
    )
    crs: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Detected source Coordinate Reference System string (e.g. 'EPSG:4326').",
    )
    feature_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Total number of features parsed from the file.",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Detailed error description if file processing failed.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        doc="UTC timestamp when the file upload was recorded.",
    )

    # Relationships: Deleting an uploaded file automatically cascades to all its features
    features: Mapped[list["Feature"]] = relationship(
        "Feature",
        back_populates="file",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Feature(Base):
    """Represents a discrete geospatial feature belonging to an UploadedFile.

    Stores both the raw geometry/attributes and computed planar measurements.
    """

    __tablename__ = "features"
    __table_args__ = (
        UniqueConstraint("file_id", "feature_index", name="uq_file_feature_index"),
        Index("ix_features_file_id", "file_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        doc="Surrogate primary key for the feature row.",
    )
    file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("uploaded_files.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key linking to the parent UploadedFile.",
    )
    feature_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Zero-based index of this feature within the source dataset.",
    )
    geometry_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Shapely geometry type (e.g. 'Polygon', 'LineString', 'Point').",
    )
    geometry: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="JSON string containing the GeoJSON representation in source CRS.",
    )
    crs: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Source coordinate reference system of this feature.",
    )
    properties: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        doc="Attribute table key-value pairs stored as JSON.",
    )
    measurement_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Measurement outcome: 'OK', 'NOT_REQUIRED', 'UNSUPPORTED', or 'ERROR'.",
    )
    area_m2: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="Measured metric planar area in square meters (polygons only).",
    )
    length_m: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="Measured metric planar length in meters (linear features only).",
    )
    projected_crs: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="EPSG code of the projected CRS used for calculation (e.g. 'EPSG:32644').",
    )
    warning: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Diagnostic warning message (e.g. if geometry was repaired).",
    )

    file: Mapped["UploadedFile"] = relationship(
        "UploadedFile",
        back_populates="features",
    )
