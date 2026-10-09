"""
Tests for app/geo/readers.py.

Verifies:
- Reading Shapefile zip archive (polygons.zip) extracts features, geometry types, and properties
- Reading KML files (polygons.kml, mixed.kml) extracts all layers with running index
- Reading projected Shapefile (projected_utm.zip) reads true declared CRS (EPSG:32643) without assuming EPSG:4326
- Archive with missing .prj (no_prj.zip) raises InvalidFileError without guessing
- Corrupted archive (corrupt.zip) raises InvalidFileError
- Malicious zip containing zip-slip or traversal payload is strictly rejected
- Unsupported file extension raises InvalidFileError
"""

import zipfile
from pathlib import Path

import pytest

from app.core.errors import InvalidFileError
from app.geo.readers import read_features, safe_extract_zip

SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def test_read_shapefile_polygons_zip() -> None:
    """Reading polygons.zip extracts 2 features with Polygon geometry and EPSG:4326 CRS."""
    zip_path = SAMPLE_DATA_DIR / "polygons.zip"
    features = read_features(zip_path)

    assert len(features) == 2

    # Feature 0: 1km square
    f0 = features[0]
    assert f0.index == 0
    assert f0.geometry is not None
    assert f0.geometry.geom_type == "Polygon"
    assert "4326" in f0.source_crs
    assert f0.properties["name"] == "1km_square"
    assert f0.properties["category"] == "farmland"

    # Feature 1: polygon with hole
    f1 = features[1]
    assert f1.index == 1
    assert f1.geometry is not None
    assert f1.geometry.geom_type == "Polygon"
    assert len(f1.geometry.interiors) == 1  # Verify hole is present
    assert "4326" in f1.source_crs
    assert f1.properties["name"] == "holed_polygon"


def test_read_kml_polygons() -> None:
    """Reading polygons.kml extracts 2 features in EPSG:4326."""
    kml_path = SAMPLE_DATA_DIR / "polygons.kml"
    features = read_features(kml_path)

    assert len(features) == 2
    for idx, feat in enumerate(features):
        assert feat.index == idx
        assert feat.geometry is not None
        assert feat.geometry.geom_type == "Polygon"
        assert feat.source_crs == "EPSG:4326"
        assert isinstance(feat.properties, dict)


def test_read_mixed_kml() -> None:
    """Reading mixed.kml extracts Point, LineString, and Polygon with running indices."""
    kml_path = SAMPLE_DATA_DIR / "mixed.kml"
    features = read_features(kml_path)

    assert len(features) == 3

    geom_types = [f.geometry.geom_type for f in features if f.geometry is not None]
    assert "Point" in geom_types
    assert "LineString" in geom_types
    assert "Polygon" in geom_types

    # Indices must be strictly monotonically increasing (0, 1, 2)
    assert [f.index for f in features] == [0, 1, 2]

    # Verify all are EPSG:4326
    for f in features:
        assert f.source_crs == "EPSG:4326"


def test_read_projected_utm_reads_explicit_crs() -> None:
    """PROVE WE READ CRS: projected_utm.zip must be detected as EPSG:32643, never assumed as 4326."""
    zip_path = SAMPLE_DATA_DIR / "projected_utm.zip"
    features = read_features(zip_path)

    assert len(features) == 1
    feat = features[0]
    assert feat.geometry is not None
    assert feat.geometry.geom_type == "Polygon"
    assert feat.source_crs == "EPSG:32643"
    assert feat.properties["name"] == "delhi_plot"
    assert feat.properties["owner"] == "Municipal Corp"


def test_missing_prj_raises_invalid_file_error() -> None:
    """Missing .prj file must fail loudly; the system must NOT guess the CRS."""
    zip_path = SAMPLE_DATA_DIR / "no_prj.zip"

    with pytest.raises(InvalidFileError) as exc_info:
        read_features(zip_path)

    assert "missing .prj" in str(exc_info.value).lower()


def test_corrupt_zip_raises_invalid_file_error() -> None:
    """Corrupted zip archive must raise InvalidFileError."""
    zip_path = SAMPLE_DATA_DIR / "corrupt.zip"

    with pytest.raises(InvalidFileError) as exc_info:
        read_features(zip_path)

    assert "corrupt" in str(exc_info.value).lower() or "zip" in str(exc_info.value).lower()


def test_unsupported_suffix_raises_invalid_file_error() -> None:
    """Unsupported file extension (e.g. .geojson, .csv) must raise InvalidFileError."""
    fake_path = Path("sample_data/unsupported.geojson")

    with pytest.raises(InvalidFileError) as exc_info:
        read_features(fake_path)

    assert "unsupported file extension" in str(exc_info.value).lower()


def test_zip_slip_rejection(tmp_path: Path) -> None:
    """Malicious zip archives with path traversal (zip-slip) must be rejected."""
    # 1. Create a zip with parent directory traversal
    malicious_zip = tmp_path / "malicious.zip"
    with zipfile.ZipFile(malicious_zip, "w") as zf:
        zf.writestr("../evil.txt", "malicious payload")

    extract_dest = tmp_path / "extracted"
    extract_dest.mkdir()

    with pytest.raises(InvalidFileError) as exc_info:
        safe_extract_zip(malicious_zip, extract_dest)

    assert "zip-slip" in str(exc_info.value).lower() or "traversal" in str(exc_info.value).lower()

    # 2. Also verify through read_features
    with pytest.raises(InvalidFileError):
        read_features(malicious_zip)
