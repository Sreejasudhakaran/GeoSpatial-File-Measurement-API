"""
Tests for app/geo/measurements.py.

Verifies:
- 1 km x 1 km square near Hyderabad matches 1,000,000 m² and pyproj.Geod within 1%
- Polygon with interior hole subtracts hole area
- MultiPolygon area equals the sum of component polygon areas
- LineString of known angular distance (0.01° latitude ~ 1,106 m) is within 1%
- Point/MultiPoint return status NOT_REQUIRED with no area or length
- GeometryCollection and empty geometries return status UNSUPPORTED
- Invalid bowtie polygon is repaired, retains warning, and produces positive area
- Proves the 'degree trap': raw geometry.area in EPSG:4326 is NOT metric area
"""

import pyproj
import pytest
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)

from app.geo.measurements import measure
from app.geo.models import (
    STATUS_NOT_REQUIRED,
    STATUS_OK,
    STATUS_UNSUPPORTED,
)


def test_square_1km_hyderabad_area_and_geod_crosscheck() -> None:
    """Measure a ~1 km x 1 km square near Hyderabad (78.49°E, 17.38°N).

    Verifies:
    1. Projected area is within 1% of the true 1,000,000 m² (1 km²).
    2. Cross-checked against pyproj.Geod ellipsoidal area within 1%.
       (UTM scale factor off the central meridian differs from geodesic by ~0.1-0.3%).
    """
    geod = pyproj.Geod(ellps="WGS84")
    lon0, lat0 = 78.49, 17.38

    # Project 1,000 meters East (azimuth 90°) and 1,000 meters North (azimuth 0°)
    lon1, _, _ = geod.fwd(lon0, lat0, 90, 1000.0)
    _, lat1, _ = geod.fwd(lon0, lat0, 0, 1000.0)

    square_poly = Polygon([
        (lon0, lat0),
        (lon1, lat0),
        (lon1, lat1),
        (lon0, lat1),
        (lon0, lat0),
    ])

    # Geodesic ground-truth area on the WGS84 ellipsoid
    geod_area, _ = geod.geometry_area_perimeter(square_poly)
    geod_area = abs(geod_area)

    result = measure(square_poly, "EPSG:4326")

    assert result.status == STATUS_OK
    assert result.area_m2 is not None
    assert result.length_m is None
    assert result.projected_crs == "EPSG:32644"

    # Within 1% of 1 km² (1,000,000 m²)
    expected_nominal = 1_000_000.0
    assert result.area_m2 == pytest.approx(expected_nominal, rel=0.01)

    # Within 1% of geodesic calculation
    assert result.area_m2 == pytest.approx(geod_area, rel=0.01)


def test_polygon_with_hole() -> None:
    """A polygon with an interior hole must have hole area subtracted."""
    # Outer rectangle: 0.02° x 0.02° near Hyderabad
    outer_coords = [
        (78.48, 17.38),
        (78.50, 17.38),
        (78.50, 17.40),
        (78.48, 17.40),
        (78.48, 17.38),
    ]
    # Hole inside: 0.005° x 0.005°
    hole_coords = [
        (78.485, 17.385),
        (78.490, 17.385),
        (78.490, 17.390),
        (78.485, 17.390),
        (78.485, 17.385),
    ]

    solid_poly = Polygon(outer_coords)
    holed_poly = Polygon(outer_coords, holes=[hole_coords])
    hole_as_poly = Polygon(hole_coords)

    m_solid = measure(solid_poly, "EPSG:4326")
    m_holed = measure(holed_poly, "EPSG:4326")
    m_hole = measure(hole_as_poly, "EPSG:4326")

    assert m_solid.area_m2 is not None
    assert m_holed.area_m2 is not None
    assert m_hole.area_m2 is not None

    # Area with hole must equal solid area minus hole area
    assert m_holed.area_m2 == pytest.approx(m_solid.area_m2 - m_hole.area_m2, rel=1e-5)


def test_multipolygon_area_is_sum_of_parts() -> None:
    """The area of a MultiPolygon must equal the sum of its individual polygons."""
    poly1 = Polygon([
        (78.48, 17.38),
        (78.49, 17.38),
        (78.49, 17.39),
        (78.48, 17.39),
        (78.48, 17.38),
    ])
    poly2 = Polygon([
        (78.51, 17.38),
        (78.52, 17.38),
        (78.52, 17.39),
        (78.51, 17.39),
        (78.51, 17.38),
    ])
    multi_poly = MultiPolygon([poly1, poly2])

    m1 = measure(poly1, "EPSG:4326")
    m2 = measure(poly2, "EPSG:4326")
    m_multi = measure(multi_poly, "EPSG:4326")

    assert m_multi.status == STATUS_OK
    assert m1.area_m2 is not None and m2.area_m2 is not None
    assert m_multi.area_m2 == pytest.approx(m1.area_m2 + m2.area_m2, rel=1e-5)


def test_linestring_known_length() -> None:
    """A LineString spanning 0.01° latitude is ~1,106.7 m on the WGS84 ellipsoid."""
    # 0.01 degrees North along the 78.49°E meridian at 17.38°N
    line = LineString([(78.49, 17.38), (78.49, 17.39)])

    result = measure(line, "EPSG:4326")

    assert result.status == STATUS_OK
    assert result.area_m2 is None
    assert result.length_m is not None

    # True ellipsoidal arc length is ~1,106.7 m; check within 1%
    expected_length = 1106.7
    assert result.length_m == pytest.approx(expected_length, rel=0.01)


def test_point_returns_not_required() -> None:
    """Point geometries have no area or length; must return status NOT_REQUIRED."""
    pt = Point(78.49, 17.38)
    res_pt = measure(pt, "EPSG:4326")
    assert res_pt.status == STATUS_NOT_REQUIRED
    assert res_pt.area_m2 is None
    assert res_pt.length_m is None

    mpt = MultiPoint([(78.49, 17.38), (78.50, 17.39)])
    res_mpt = measure(mpt, "EPSG:4326")
    assert res_mpt.status == STATUS_NOT_REQUIRED
    assert res_mpt.area_m2 is None
    assert res_mpt.length_m is None


def test_unsupported_geometries() -> None:
    """GeometryCollection and empty geometries must gracefully return UNSUPPORTED."""
    # GeometryCollection is not a pure polygonal or linear type
    gc = GeometryCollection([Point(0, 0), LineString([(0, 0), (1, 1)])])
    res_gc = measure(gc, "EPSG:4326")
    assert res_gc.status == STATUS_UNSUPPORTED
    assert res_gc.area_m2 is None
    assert res_gc.length_m is None

    # Empty geometry
    empty_poly = Polygon()
    res_empty = measure(empty_poly, "EPSG:4326")
    assert res_empty.status == STATUS_UNSUPPORTED
    assert res_empty.warning == "empty geometry"


def test_self_intersecting_bowtie_polygon_repaired() -> None:
    """Self-intersecting polygon is repaired via make_valid with warning and valid area."""
    # Classic self-intersecting bowtie figure-eight polygon
    bowtie = Polygon([
        (78.49, 17.38),
        (78.49, 17.40),
        (78.51, 17.38),
        (78.51, 17.40),
        (78.49, 17.38),
    ])
    assert not bowtie.is_valid

    result = measure(bowtie, "EPSG:4326")

    assert result.status == STATUS_OK
    assert result.warning is not None
    assert "geometry was invalid and repaired" in result.warning
    assert result.area_m2 is not None
    assert result.area_m2 > 0.0


def test_prove_the_degree_trap() -> None:
    """PROVE THE TRAP: Never compute area in lat/lon degrees.

    Calling raw shapely geometry.area on EPSG:4326 coordinates calculates
    area in square degrees (e.g. ~0.0001 deg²), which is completely meaningless
    as metric area (~1,000,000 m²). The two numbers differ by 10 orders of magnitude.
    """
    poly = Polygon([
        (78.49, 17.38),
        (78.50, 17.38),
        (78.50, 17.39),
        (78.49, 17.39),
        (78.49, 17.38),
    ])

    raw_degree_area = poly.area  # In (degrees)² ~ 0.0001
    result = measure(poly, "EPSG:4326")

    assert result.status == STATUS_OK
    assert result.area_m2 is not None

    # Raw area in square degrees is NOT metric area in square meters!
    assert raw_degree_area != result.area_m2
    # Verify the massive order-of-magnitude difference:
    assert raw_degree_area < 1.0  # Fraction of a square degree
    assert result.area_m2 > 1_000_000.0  # Over 1 million square meters
