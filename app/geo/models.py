"""
Domain models for geospatial extraction and measurements.

PURE MODELS ONLY:
This module defines in-memory dataclasses used by the geo processing layer.
It must NEVER import FastAPI or SQLAlchemy.
"""

from dataclasses import dataclass, field
from typing import Any
from shapely.geometry.base import BaseGeometry

# Status constants for measurements
STATUS_OK = "OK"
STATUS_NOT_REQUIRED = "NOT_REQUIRED"
STATUS_UNSUPPORTED = "UNSUPPORTED"
STATUS_ERROR = "ERROR"

# Shorthand aliases for external callers
OK = STATUS_OK
NOT_REQUIRED = STATUS_NOT_REQUIRED
UNSUPPORTED = STATUS_UNSUPPORTED
ERROR = STATUS_ERROR


@dataclass
class Measurement:
    """Represents the measurement outcome for a single geospatial geometry.

    Attributes:
        status: One of OK, NOT_REQUIRED, UNSUPPORTED, ERROR.
        area_m2: Area in square meters for polygonal geometries; None otherwise.
        length_m: Length in meters for linear geometries; None otherwise.
        projected_crs: EPSG code of the projected CRS used for calculation.
        warning: Diagnostic warning (e.g., if geometry was repaired or unsupported).
    """

    status: str
    area_m2: float | None = None
    length_m: float | None = None
    projected_crs: str | None = None
    warning: str | None = None


@dataclass
class FeatureRecord:
    """Represents a feature extracted directly from a geospatial dataset.

    Attributes:
        index: Zero-based feature index within the source file.
        geometry: Shapely geometry in its SOURCE coordinate reference system.
        source_crs: The CRS declared or detected in the source file.
        properties: Feature attribute table dictionary.
    """

    index: int
    geometry: BaseGeometry | None
    source_crs: str
    properties: dict[str, Any] = field(default_factory=dict)
