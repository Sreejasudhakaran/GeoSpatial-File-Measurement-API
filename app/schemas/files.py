"""
Pydantic schemas for file upload, metadata, and measurement responses.

Follows Pydantic V2 style using BaseModel and ConfigDict.
"""

from datetime import datetime
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FileResponse(BaseModel):
    """Metadata response representing an uploaded file."""

    id: str
    filename: str
    file_type: str
    feature_count: int
    crs: str | None = None
    status: str
    error_message: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MeasurementItem(BaseModel):
    """Single feature measurement record."""

    feature_index: int
    geometry_type: str
    crs: str
    geometry: dict[str, Any] | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    measurement_status: str
    area_m2: float | None = None
    length_m: float | None = None
    projected_crs: str | None = None
    warning: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("geometry", mode="before")
    @classmethod
    def parse_geometry_json(cls, v: Any) -> Any:
        """Parse raw GeoJSON string from the database column into a JSON dictionary."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v


class MeasurementsResponse(BaseModel):
    """Paginated collection of feature measurements for an uploaded file."""

    file_id: str
    total: int
    limit: int
    offset: int
    items: list[MeasurementItem]
