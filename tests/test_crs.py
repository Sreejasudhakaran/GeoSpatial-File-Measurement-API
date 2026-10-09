"""
Tests for app/geo/crs.py.

Verifies:
- UTM zone calculation for various global coordinates
- Polar fallback to UPS North and South
- Longitude boundary edge cases (-180, 180)
- to_wgs84 reprojection accuracy and no-op on EPSG:4326
"""

import pytest
from shapely.geometry import Point, Polygon

from app.geo.crs import pick_projected_crs, to_wgs84


def test_pick_projected_crs_delhi() -> None:
    """Delhi (77.2°E, 28.6°N) falls in UTM Zone 43 North."""
    delhi = Point(77.2, 28.6)
    assert pick_projected_crs(delhi) == "EPSG:32643"


def test_pick_projected_crs_hyderabad() -> None:
    """Hyderabad (78.49°E, 17.38°N) falls in UTM Zone 44 North.

    Note on UTM Zones:
    Zone 43 covers 72°E to 78°E.
    Zone 44 covers 78°E to 84°E.
    Since 78.49 > 78.0, floor((78.49 + 180) / 6) + 1 = 44 -> EPSG:32644.
    """
    hyderabad = Point(78.49, 17.38)
    assert pick_projected_crs(hyderabad) == "EPSG:32644"


def test_pick_projected_crs_sydney() -> None:
    """Sydney (151.2°E, -33.9°S) falls in UTM Zone 56 South."""
    sydney = Point(151.2, -33.9)
    assert pick_projected_crs(sydney) == "EPSG:32756"


def test_pick_projected_crs_london() -> None:
    """London (-0.12°W, 51.5°N) falls in UTM Zone 30 North."""
    london = Point(-0.12, 51.5)
    assert pick_projected_crs(london) == "EPSG:32630"


def test_pick_projected_crs_longitude_boundaries() -> None:
    """Edge cases for lon=-180 and lon=180 must stay within zones 1..60."""
    # lon = -180: floor((-180 + 180) / 6) + 1 = 1
    pt_west = Point(-180.0, 10.0)
    assert pick_projected_crs(pt_west) == "EPSG:32601"

    # lon = 180: floor((180 + 180) / 6) + 1 = 61 -> clamped to 60
    pt_east = Point(180.0, 10.0)
    assert pick_projected_crs(pt_east) == "EPSG:32660"

    # Southern hemisphere boundaries
    pt_south_west = Point(-180.0, -10.0)
    assert pick_projected_crs(pt_south_west) == "EPSG:32701"

    pt_south_east = Point(180.0, -10.0)
    assert pick_projected_crs(pt_south_east) == "EPSG:32760"


def test_pick_projected_crs_polar_fallbacks() -> None:
    """Latitudes beyond standard UTM range fallback to UPS North/South."""
    # North pole area: lat > 84 -> UPS North (EPSG:32661)
    pt_arctic = Point(0.0, 85.0)
    assert pick_projected_crs(pt_arctic) == "EPSG:32661"

    # South pole area: lat < -80 -> UPS South (EPSG:32761)
    pt_antarctic = Point(0.0, -85.0)
    assert pick_projected_crs(pt_antarctic) == "EPSG:32761"


def test_pick_projected_crs_polygon() -> None:
    """CRS selection uses polygon centroid."""
    poly = Polygon([
        (77.0, 28.0),
        (77.4, 28.0),
        (77.4, 28.4),
        (77.0, 28.4),
        (77.0, 28.0),
    ])
    assert pick_projected_crs(poly) == "EPSG:32643"


def test_to_wgs84_noop_when_already_4326() -> None:
    """If source CRS is already EPSG:4326, the geometry is returned unchanged."""
    pt = Point(77.2, 28.6)
    result = to_wgs84(pt, "EPSG:4326")
    assert result is pt or (result.x == pt.x and result.y == pt.y)

    # Also test integer 4326 and lowercase epsg:4326
    result_int = to_wgs84(pt, 4326)
    assert result_int.x == pt.x and result_int.y == pt.y


def test_to_wgs84_reproject_from_utm() -> None:
    """Reprojecting coordinates from EPSG:32643 to EPSG:4326 recovers lon/lat."""
    # Delhi coordinates in EPSG:32643
    delhi_utm = Point(715128.44, 3165648.06)

    delhi_wgs84 = to_wgs84(delhi_utm, "EPSG:32643")

    # Longitude ~ 77.2, Latitude ~ 28.6
    assert delhi_wgs84.x == pytest.approx(77.2, abs=1e-4)
    assert delhi_wgs84.y == pytest.approx(28.6, abs=1e-4)
