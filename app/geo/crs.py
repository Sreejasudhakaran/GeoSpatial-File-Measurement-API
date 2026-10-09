"""
Coordinate Reference System (CRS) selection and reprojection utilities.

PURE FUNCTIONS ONLY:
This module contains domain-level geospatial math.
It must NEVER import FastAPI or SQLAlchemy.

KNOWN LIMITATIONS:
1. Multi-zone features: Features spanning multiple UTM zones are projected
   into the zone of their centroid. While suitable for local measurements,
   very large features (e.g. continental lines or multi-state polygons) will
   experience scale distortion away from the central meridian.
2. Special UTM zone exceptions: Standard UTM grid rules are applied strictly.
   Regional UTM exceptions such as UTM 32V (southwestern Norway) and
   zones 31X, 33X, 35X, 37X (Svalbard) are NOT handled.
"""

import math
from typing import Any

import pyproj
import shapely
from shapely.geometry.base import BaseGeometry


def pick_projected_crs(geometry_wgs84: BaseGeometry) -> str:
    """Select a suitable projected CRS (in meters) for a geometry in EPSG:4326.

    Strategy:
    1. Extract the centroid (lon, lat) of the input geometry.
    2. Check polar regions:
       - lat > 84 degrees: Universal Polar Stereographic North (EPSG:32661)
       - lat < -80 degrees: Universal Polar Stereographic South (EPSG:32761)
    3. For non-polar latitudes, calculate the UTM zone:
       zone = floor((lon + 180) / 6) + 1, clamped to [1, 60].
    4. Return EPSG:326{zone:02d} for northern hemisphere (lat >= 0),
       or EPSG:327{zone:02d} for southern hemisphere (lat < 0).

    Args:
        geometry_wgs84: Shapely geometry whose coordinates are in EPSG:4326 (lon, lat).

    Returns:
        A projected CRS identifier string, e.g. 'EPSG:32643'.
    """
    if geometry_wgs84.is_empty:
        # Default fallback for empty geometry
        return "EPSG:3857"

    centroid = geometry_wgs84.centroid
    lon = centroid.x
    lat = centroid.y

    # Polar fallbacks (UTM is only defined between 80°S and 84°N)
    if lat > 84.0:
        return "EPSG:32661"  # UPS North
    if lat < -80.0:
        return "EPSG:32761"  # UPS South

    # Standard UTM calculation
    # Range of UTM zones is 1 to 60 (each 6 degrees wide)
    raw_zone = math.floor((lon + 180.0) / 6.0) + 1
    zone = max(1, min(60, int(raw_zone)))

    if lat >= 0.0:
        return f"EPSG:326{zone:02d}"
    return f"EPSG:327{zone:02d}"


def to_wgs84(geometry: BaseGeometry, source_crs: Any) -> BaseGeometry:
    """Reproject a Shapely geometry from source_crs to EPSG:4326 (WGS84 lon, lat).

    If source_crs is already EPSG:4326, the geometry is returned unchanged.

    Args:
        geometry: Shapely geometry in source_crs coordinates.
        source_crs: The source CRS (e.g. 'EPSG:32643', EPSG integer, or pyproj.CRS).

    Returns:
        Transformed Shapely geometry in EPSG:4326 (lon, lat).
    """
    if geometry.is_empty:
        return geometry

    crs = pyproj.CRS.from_user_input(source_crs)
    # If already WGS 84 (EPSG:4326), no transformation needed
    if crs.to_epsg() == 4326:
        return geometry

    transformer = pyproj.Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    return shapely.transform(
        geometry,
        transformer.transform,
        interleaved=False,
        include_z=bool(geometry.has_z),
    )
