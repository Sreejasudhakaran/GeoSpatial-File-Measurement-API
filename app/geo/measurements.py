"""
Pure geospatial measurement engine.

PURE FUNCTIONS ONLY:
Computes metric area and length by reprojecting geometries into optimal
local projected coordinate reference systems (UTM/UPS).
This module must NEVER import FastAPI or SQLAlchemy.
"""

from typing import Any

import pyproj
import shapely
import shapely.validation
from shapely.geometry import (
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry

from app.geo.crs import pick_projected_crs, to_wgs84
from app.geo.models import (
    STATUS_ERROR,
    STATUS_NOT_REQUIRED,
    STATUS_OK,
    STATUS_UNSUPPORTED,
    Measurement,
)


def measure(geometry: BaseGeometry | None, source_crs: Any) -> Measurement:
    """Measure a geometry in metric units using a suitable projected CRS.

    Rules:
    - null or empty geometry -> UNSUPPORTED (warning: 'empty geometry')
    - 3D coordinates are flattened to 2D via shapely.force_2d
    - Reprojected to WGS84, then reprojected into a local projected CRS (UTM/UPS)
    - Polygon / MultiPolygon -> area in square meters (holes are subtracted)
    - LineString / MultiLineString -> length in meters
    - Point / MultiPoint -> NOT_REQUIRED (no area or length)
    - GeometryCollection or other unhandled types -> UNSUPPORTED
    - Invalid geometries are repaired with shapely.validation.make_valid;
      if a repaired polygon degenerates into a non-polygonal geometry,
      it returns UNSUPPORTED.
    - Wrapped in try/except: never raises an unhandled exception.

    Args:
        geometry: Shapely geometry object (or None).
        source_crs: The declared CRS of the source dataset.

    Returns:
        A Measurement dataclass instance.
    """
    # 1. Guard against None or empty geometries
    if geometry is None or geometry.is_empty:
        return Measurement(
            status=STATUS_UNSUPPORTED,
            area_m2=None,
            length_m=None,
            projected_crs=None,
            warning="empty geometry",
        )

    try:
        # 2. Drop Z coordinate (measurements are planar 2D)
        geom_2d = shapely.force_2d(geometry)

        # 3. Convert from source CRS to WGS84 (lon, lat)
        geom_wgs84 = to_wgs84(geom_2d, source_crs)

        # 4. Determine optimal projected CRS (UTM / UPS)
        projected_crs = pick_projected_crs(geom_wgs84)

        # 5. Transform from WGS84 to the chosen projected CRS
        transformer = pyproj.Transformer.from_crs("EPSG:4326", projected_crs, always_xy=True)
        proj_geom = shapely.transform(geom_wgs84, transformer.transform, interleaved=False)

        warning_msgs: list[str] = []
        is_originally_polygonal = isinstance(proj_geom, (Polygon, MultiPolygon))

        # 6. Check and repair geometric validity if needed
        if not proj_geom.is_valid:
            proj_geom = shapely.validation.make_valid(proj_geom)
            warning_msgs.append("geometry was invalid and repaired")

            # If the repair degenerated a polygon into lines/points, measurement cannot proceed
            if is_originally_polygonal and not isinstance(proj_geom, (Polygon, MultiPolygon)):
                warning_msgs.append("repair result is not polygonal")
                return Measurement(
                    status=STATUS_UNSUPPORTED,
                    area_m2=None,
                    length_m=None,
                    projected_crs=projected_crs,
                    warning="; ".join(warning_msgs),
                )

        warning = "; ".join(warning_msgs) if warning_msgs else None

        # 7. Compute measurement according to geometry type
        if isinstance(proj_geom, (Polygon, MultiPolygon)):
            return Measurement(
                status=STATUS_OK,
                area_m2=float(proj_geom.area),
                length_m=None,
                projected_crs=projected_crs,
                warning=warning,
            )

        if isinstance(proj_geom, (LineString, MultiLineString)):
            return Measurement(
                status=STATUS_OK,
                area_m2=None,
                length_m=float(proj_geom.length),
                projected_crs=projected_crs,
                warning=warning,
            )

        if isinstance(proj_geom, (Point, MultiPoint)):
            return Measurement(
                status=STATUS_NOT_REQUIRED,
                area_m2=None,
                length_m=None,
                projected_crs=projected_crs,
                warning=warning,
            )

        # 8. Unhandled geometry types (e.g. GeometryCollection, LinearRing)
        return Measurement(
            status=STATUS_UNSUPPORTED,
            area_m2=None,
            length_m=None,
            projected_crs=projected_crs,
            warning=warning or f"unsupported geometry type: {proj_geom.geom_type}",
        )

    except Exception as exc:  # noqa: BLE001 - isolation guarantee: never raise on bad geometry
        # 9. Total isolation guarantee: Never crash or raise an unhandled exception
        return Measurement(
            status=STATUS_ERROR,
            area_m2=None,
            length_m=None,
            projected_crs=None,
            warning=f"measurement failed: {exc!s}",
        )
