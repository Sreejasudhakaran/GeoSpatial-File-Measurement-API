"""
Geospatial file reading and feature extraction.

PURE FUNCTIONS ONLY:
Parses Shapefile archives (.zip) and KML files (.kml).
Extracts geometry, CRS, and JSON-serializable properties per feature.
This module must NEVER import FastAPI or SQLAlchemy.
"""

import datetime
import math
from pathlib import Path
import tempfile
from typing import Any
import zipfile

import numpy as np
import pandas as pd
import pyogrio
import pyproj
from shapely.geometry.base import BaseGeometry

from app.core.errors import InvalidFileError
from app.geo.models import FeatureRecord


def safe_extract_zip(zip_path: Path, dest: Path) -> None:
    """Extract a zip archive safely, preventing zip-slip vulnerabilities.

    Rejects:
    - Any archive member resolving outside dest
    - Members containing relative parent traversals ('..')
    - Members with absolute paths

    Args:
        zip_path: Path to the .zip archive.
        dest: Target destination directory for extraction.

    Raises:
        InvalidFileError: If the zip is corrupt or contains a zip-slip payload.
    """
    dest_resolved = dest.resolve()

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                member_path = Path(member.filename)

                # Disallow absolute paths
                if member_path.is_absolute() or member.filename.startswith(("/", "\\")):
                    raise InvalidFileError(
                        f"malicious zip entry detected (absolute path): {member.filename}"
                    )

                # Disallow parent path traversals
                if ".." in member_path.parts:
                    raise InvalidFileError(
                        f"malicious zip entry detected (path traversal): {member.filename}"
                    )

                target_path = (dest / member.filename).resolve()

                # Verify target path stays strictly inside dest directory
                if not (target_path == dest_resolved or target_path.is_relative_to(dest_resolved)):
                    raise InvalidFileError(
                        f"malicious zip entry detected (zip-slip): {member.filename}"
                    )

            zf.extractall(dest)

    except zipfile.BadZipFile as exc:
        raise InvalidFileError(f"corrupt or unreadable zip archive: {exc}")
    except InvalidFileError:
        raise
    except Exception as exc:
        raise InvalidFileError(f"failed to extract zip archive: {exc}")


def find_shapefile(extract_dir: Path) -> Path:
    """Find the main .shp file in an extracted archive directory.

    Searches recursively to support archives where the shapefile is contained
    within a subdirectory. Ignores macOS system metadata folders (__MACOSX)
    and hidden files.

    Args:
        extract_dir: The directory containing extracted archive contents.

    Returns:
        Path to the found .shp file.

    Raises:
        InvalidFileError: If no valid .shp file is found.
    """
    shp_files = [
        p for p in extract_dir.rglob("*.shp")
        if "__MACOSX" not in p.parts and not p.name.startswith("._")
    ]

    if not shp_files:
        raise InvalidFileError("no .shp found in zip")

    return shp_files[0]


def _serialize_value(val: Any) -> Any:
    """Convert pandas/numpy values into standard JSON-serializable Python types."""
    if val is None or pd.isna(val):
        return None

    if isinstance(val, (pd.Timestamp, datetime.datetime, datetime.date)):
        return val.isoformat()

    if isinstance(val, (np.integer, int)):
        return int(val)

    if isinstance(val, (np.floating, float)):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)

    if isinstance(val, (np.bool_, bool)):
        return bool(val)

    if isinstance(val, (dict, list)):
        return val

    return str(val)


def _extract_properties(row: pd.Series, columns: Any) -> dict[str, Any]:
    """Extract and serialize non-geometry feature attributes from a dataframe row."""
    properties: dict[str, Any] = {}
    for col in columns:
        if col == "geometry":
            continue
        properties[col] = _serialize_value(row[col])
    return properties


def read_shapefile_archive(zip_path: Path) -> list[FeatureRecord]:
    """Extract a shapefile zip archive and return all features."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        safe_extract_zip(zip_path, tmp_path)
        shp_path = find_shapefile(tmp_path)

        try:
            df = pyogrio.read_dataframe(shp_path)
        except Exception as exc:
            raise InvalidFileError(f"failed to read shapefile: {exc}")

        # Check for missing .prj file
        if df.crs is None:
            raise InvalidFileError(
                "missing .prj file: coordinate reference system (CRS) cannot be determined; do not guess"
            )

        source_crs = pyproj.CRS.from_user_input(df.crs).to_string()

        records: list[FeatureRecord] = []
        for idx, row in df.iterrows():
            geom = row.geometry if hasattr(row, "geometry") else None
            if geom is not None and pd.isna(geom):
                geom = None

            properties = _extract_properties(row, df.columns)
            records.append(
                FeatureRecord(
                    index=int(idx),
                    geometry=geom,
                    source_crs=source_crs,
                    properties=properties,
                )
            )

        return records


def read_kml(path: Path) -> list[FeatureRecord]:
    """Read all layers from a KML file and return all features.

    KML folders translate to multiple layers in OGR. All layers are read,
    and a running index counter guarantees globally unique feature indices.
    KML is defined strictly in WGS84 (EPSG:4326).
    """
    try:
        layers = pyogrio.list_layers(path)
    except Exception as exc:
        raise InvalidFileError(f"failed to read KML layers: {exc}")

    if len(layers) == 0:
        raise InvalidFileError("KML file contains no layers")

    layer_names = [row[0] for row in layers] if len(layers.shape) == 2 else [layers[0]]

    records: list[FeatureRecord] = []
    current_index = 0

    for layer_name in layer_names:
        try:
            df = pyogrio.read_dataframe(path, layer=layer_name)
        except Exception as exc:
            raise InvalidFileError(f"failed to read KML layer '{layer_name}': {exc}")

        for _, row in df.iterrows():
            geom = row.geometry if hasattr(row, "geometry") else None
            if geom is not None and pd.isna(geom):
                geom = None

            properties = _extract_properties(row, df.columns)
            records.append(
                FeatureRecord(
                    index=current_index,
                    geometry=geom,
                    source_crs="EPSG:4326",
                    properties=properties,
                )
            )
            current_index += 1

    return records


def read_features(path: Path) -> list[FeatureRecord]:
    """Dispatch reader based on file extension (.zip for shapefile, .kml).

    Args:
        path: Path to the geospatial file on disk.

    Returns:
        List of FeatureRecord instances.

    Raises:
        InvalidFileError: If file is unsupported, missing essential components,
                          or structurally unreadable.
    """
    suffix = path.suffix.lower()

    if suffix == ".zip":
        return read_shapefile_archive(path)
    elif suffix == ".kml":
        return read_kml(path)
    else:
        raise InvalidFileError(f"unsupported file extension: {suffix}. Expected .zip or .kml")
