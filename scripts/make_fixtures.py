"""
Generate tiny sample geospatial datasets in sample_data/ for testing and demos.

Datasets created:
1. polygons.kml and polygons.zip (EPSG:4326):
   - 1 km x 1 km square near Hyderabad
   - Polygon with an interior hole
2. mixed.kml (EPSG:4326):
   - Point, LineString, and Polygon
3. projected_utm.zip (EPSG:32643):
   - Shapefile explicitly projected in UTM 43N
4. no_prj.zip:
   - Shapefile archive missing the .prj file to test strict CRS validation
5. corrupt.zip:
   - Random non-zip bytes to test corrupted upload handling
"""

import os
from pathlib import Path
import tempfile
import zipfile

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon


def create_zip_from_dir(source_dir: Path, zip_dest: Path, exclude_extensions: tuple[str, ...] = ()) -> None:
    """Helper to zip all files in source_dir into zip_dest, optionally excluding extensions."""
    with zipfile.ZipFile(zip_dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(source_dir):
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix in exclude_extensions:
                    continue
                arcname = file_path.relative_to(source_dir)
                zf.write(file_path, arcname)


def make_fixtures(output_dir: Path) -> None:
    """Generate all test fixtures inside output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------
    # 1. polygons (1km square near Hyderabad + a polygon with a hole)
    # -------------------------------------------------------------
    # 1 km square: ~0.00941° lon x ~0.00904° lat near Hyderabad (78.49°E, 17.38°N)
    sq_poly = Polygon([
        (78.4900, 17.3800),
        (78.4994, 17.3800),
        (78.4994, 17.3890),
        (78.4900, 17.3890),
        (78.4900, 17.3800),
    ])

    # Polygon with interior hole
    outer_coords = [
        (78.510, 17.380),
        (78.530, 17.380),
        (78.530, 17.400),
        (78.510, 17.400),
        (78.510, 17.380),
    ]
    hole_coords = [
        (78.515, 17.385),
        (78.525, 17.385),
        (78.525, 17.395),
        (78.515, 17.395),
        (78.515, 17.385),
    ]
    holed_poly = Polygon(outer_coords, holes=[hole_coords])

    gdf_polygons = gpd.GeoDataFrame(
        {
            "name": ["1km_square", "holed_polygon"],
            "category": ["farmland", "park"],
        },
        geometry=[sq_poly, holed_poly],
        crs="EPSG:4326",
    )

    # Save polygons.kml
    kml_path = output_dir / "polygons.kml"
    gdf_polygons.to_file(kml_path, driver="KML")

    # Save polygons.zip
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_shp = Path(tmp_dir) / "polygons.shp"
        gdf_polygons.to_file(tmp_shp)
        create_zip_from_dir(Path(tmp_dir), output_dir / "polygons.zip")

    # -------------------------------------------------------------
    # 2. mixed.kml (Point, LineString, Polygon)
    # -------------------------------------------------------------
    pt = Point(78.49, 17.38)
    line = LineString([(78.49, 17.38), (78.50, 17.39)])
    poly = Polygon([(78.50, 17.40), (78.51, 17.40), (78.51, 17.41), (78.50, 17.40)])

    gdf_mixed = gpd.GeoDataFrame(
        {
            "name": ["poi_point", "road_line", "building_poly"],
            "feat_type": ["point", "line", "polygon"],
        },
        geometry=[pt, line, poly],
        crs="EPSG:4326",
    )
    gdf_mixed.to_file(output_dir / "mixed.kml", driver="KML")

    # -------------------------------------------------------------
    # 3. projected_utm.zip (Shapefile explicitly in EPSG:32643)
    # -------------------------------------------------------------
    # Coordinates in meters in UTM 43N (around Delhi: ~715000m E, 3165000m N)
    utm_poly = Polygon([
        (715000, 3165000),
        (716000, 3165000),
        (716000, 3166000),
        (715000, 3166000),
        (715000, 3165000),
    ])
    gdf_utm = gpd.GeoDataFrame(
        {"name": ["delhi_plot"], "owner": ["Municipal Corp"]},
        geometry=[utm_poly],
        crs="EPSG:32643",
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_shp = Path(tmp_dir) / "delhi_utm.shp"
        gdf_utm.to_file(tmp_shp)
        create_zip_from_dir(Path(tmp_dir), output_dir / "projected_utm.zip")

    # -------------------------------------------------------------
    # 4. no_prj.zip (Shapefile with .prj excluded)
    # -------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_shp = Path(tmp_dir) / "no_crs.shp"
        gdf_polygons.to_file(tmp_shp)
        # Exclude .prj from the zip archive
        create_zip_from_dir(Path(tmp_dir), output_dir / "no_prj.zip", exclude_extensions=(".prj",))

    # -------------------------------------------------------------
    # 5. corrupt.zip (Random non-zip bytes)
    # -------------------------------------------------------------
    with open(output_dir / "corrupt.zip", "wb") as f:
        f.write(b"CORRUPTED_NON_ZIP_RANDOM_DATA_1234567890\x00\xff\xfe")


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "sample_data"
    make_fixtures(target)
    print(f"Fixtures successfully generated in {target}")
