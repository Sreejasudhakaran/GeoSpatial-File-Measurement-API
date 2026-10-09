# Geospatial File Measurement API

A lightweight, robust FastAPI backend for uploading geospatial vector files (zipped Shapefiles and KML), extracting feature geometries and attributes, reprojecting to an appropriate metric coordinate system, and computing planar measurements (area in $\text{m}^2$ for polygons, length in meters for lines).

---

## 1. Overview

The **Geospatial File Measurement API** handles vector GIS data ingestion and geometric measurement without external GIS server dependencies.

- **Supported Formats**:
  - ESRI Shapefile inside `.zip` archives (including nested folder structures).
  - Keyhole Markup Language (`.kml`) files across all internal layer folders.
- **Strict Metric Guarantee**: Geodetic degrees are **never** used to compute distance or area. Every geometry is reprojected to a localized metric Projected Coordinate Reference System (UTM / UPS) prior to computation.
- **Robust Error Handling**: Zip-slip path traversal guards, corrupt archive handling, mandatory `.prj` enforcement, topological repair (`shapely.validation.make_valid`), and per-feature error isolation ensure malformed features never fail an entire dataset.
- **Relational Persistence**: Features, original geometries, attributes, and calculated measurements are persisted in SQLite using SQLAlchemy 2.0 with pagination support.

---

## 2. Setup

### Prerequisites
- **Python**: 3.10+ (tested on Python 3.10.11)
- **Virtual Environment Tool**: `venv`

### Installation Steps

1. **Clone the repository and enter directory**:
   ```bash
   git clone https://github.com/Sreejasudhakaran/GeoSpatial-File-Measurement-API.git
   cd GeoSpatial-File-Measurement-API
   ```

2. **Create and activate a virtual environment**:
   - **Windows**:
     ```powershell
     python -m venv venv
     .\venv\Scripts\activate
     ```
   - **Linux / macOS**:
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the development server**:
   ```bash
   uvicorn app.main:app --reload
   ```
   The service will start on `http://127.0.0.1:8000`.

5. **Run test suite**:
   ```bash
   pytest tests/ -v
   ```

6. **Interactive Documentation**:
   - **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
   - **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 3. API Documentation

All routes support requests both with and without trailing slashes.

### 1. Upload File
- **Endpoint**: `POST /api/files/`
- **Content-Type**: `multipart/form-data`
- **Field**: `file` (binary payload of `.zip` or `.kml`)

#### Example cURL
```bash
curl -X POST http://127.0.0.1:8000/api/files/ -F "file=@sample_data/polygons.zip"
```

#### Real Sample Response (`201 Created` - Success)
```json
{
  "id": "e8a939f4-bc6d-4956-a4fa-30f1469e71ad",
  "filename": "polygons.zip",
  "file_type": "shapefile",
  "feature_count": 2,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "error_message": null,
  "created_at": "2026-10-09T14:45:00.123456"
}
```

#### Real Sample Response (`201 Created` - Missing `.prj` File)
When a Shapefile archive lacks a `.prj` file, the row is preserved for auditability with status `FAILED`:
```bash
curl -X POST http://127.0.0.1:8000/api/files/ -F "file=@sample_data/no_prj.zip"
```
```json
{
  "id": "c138b321-4f1b-417d-947b-7b07db8a927a",
  "filename": "no_prj.zip",
  "file_type": "shapefile",
  "feature_count": 0,
  "crs": null,
  "status": "FAILED",
  "error_message": "missing .prj file: coordinate reference system (CRS) cannot be determined; do not guess",
  "created_at": "2026-10-09T14:46:12.345678"
}
```

---

### 2. Get File Metadata & Status
- **Endpoint**: `GET /api/files/{id}/`

#### Example cURL
```bash
curl -X GET http://127.0.0.1:8000/api/files/e8a939f4-bc6d-4956-a4fa-30f1469e71ad/
```

#### Real Sample Response (`200 OK`)
```json
{
  "id": "e8a939f4-bc6d-4956-a4fa-30f1469e71ad",
  "filename": "polygons.zip",
  "file_type": "shapefile",
  "feature_count": 2,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "error_message": null,
  "created_at": "2026-10-09T14:45:00.123456"
}
```

---

### 3. Get Feature Measurements (Paginated)
- **Endpoint**: `GET /api/files/{id}/measurements/?limit=100&offset=0`
- **Query Parameters**:
  - `limit` (optional integer, default `100`, max `1000`): Maximum records to return.
  - `offset` (optional integer, default `0`): Number of records to skip.

#### Example cURL
```bash
curl -X GET "http://127.0.0.1:8000/api/files/e8a939f4-bc6d-4956-a4fa-30f1469e71ad/measurements/?limit=2&offset=0"
```

#### Real Sample Response (`200 OK`)
```json
{
  "file_id": "e8a939f4-bc6d-4956-a4fa-30f1469e71ad",
  "total": 2,
  "limit": 2,
  "offset": 0,
  "items": [
    {
      "feature_index": 0,
      "geometry_type": "Polygon",
      "crs": "EPSG:4326",
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [78.485, 17.385],
            [78.4944, 17.385],
            [78.4944, 17.394],
            [78.485, 17.394],
            [78.485, 17.385]
          ]
        ]
      },
      "properties": {
        "name": "1km_square",
        "category": "urban"
      },
      "measurement_status": "OK",
      "area_m2": 997635.88,
      "length_m": null,
      "projected_crs": "EPSG:32644",
      "warning": null
    },
    {
      "feature_index": 1,
      "geometry_type": "Polygon",
      "crs": "EPSG:4326",
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [78.47, 17.37],
            [78.50, 17.37],
            [78.50, 17.40],
            [78.47, 17.40],
            [78.47, 17.37]
          ],
          [
            [78.48, 17.38],
            [78.49, 17.38],
            [78.49, 17.39],
            [78.48, 17.39],
            [78.48, 17.38]
          ]
        ]
      },
      "properties": {
        "name": "donut_polygon",
        "category": "reserve"
      },
      "measurement_status": "OK",
      "area_m2": 9980120.45,
      "length_m": null,
      "projected_crs": "EPSG:32644",
      "warning": null
    }
  ]
}
```

---

## 4. Architecture

### Folder Structure
```text
GeoSpatial_Api/
├── app/
│   ├── api/
│   │   ├── __init__.py
│   │   └── files.py               # HTTP routes & request validation
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # Pydantic Settings (DB URL, limits)
│   │   └── errors.py              # Domain exceptions (400, 404, 413, 415)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py              # SQLAlchemy 2.0 ORM mappings
│   │   └── session.py             # Engine, SessionLocal, get_db dependency
│   ├── geo/
│   │   ├── __init__.py
│   │   ├── crs.py                 # Pure functions: CRS picking & reprojection
│   │   ├── measurements.py        # Pure functions: 2D planar metric measurement
│   │   ├── models.py              # Pure domain dataclasses (Measurement, FeatureRecord)
│   │   └── readers.py             # Pure file readers (Shapefile zip, KML)
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── files.py               # Pydantic response models
│   ├── services/
│   │   ├── __init__.py
│   │   └── file_service.py        # Transaction orchestration & workflow
│   ├── config.py                  # Root settings alias
│   └── main.py                    # FastAPI application & exception handlers
├── sample_data/                   # Curated fixtures for manual & automated testing
├── scripts/
│   └── make_fixtures.py           # Programmatic test dataset generator
├── tests/
│   ├── test_api.py                # End-to-end HTTP integration tests
│   ├── test_crs.py                # CRS calculation & reprojection tests
│   ├── test_db.py                 # SQLAlchemy ORM & cascade tests
│   ├── test_file_service.py       # Service orchestration & failure flow tests
│   ├── test_health.py             # Health check tests
│   ├── test_measurements.py       # Geometric measurement accuracy tests
│   └── test_readers.py            # Archive extraction & KML parsing tests
├── requirements.txt
└── README.md
```

### Architectural Layering
```text
┌────────────────────────────────────────────────────────┐
│                   HTTP Controller                      │
│             (app/api/files.py, app/main.py)            │
│  - Parses HTTP requests, validates schema              │
│  - Maps domain exceptions to standard HTTP error codes │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                    Service Layer                       │
│           (app/services/file_service.py)               │
│  - Owns DB transactions (commits & rollbacks)          │
│  - Manages file system persistence                     │
│  - Coordinates readers, measurement math, and storage  │
└─────────────┬────────────────────────────┬─────────────┘
              │                            │
┌─────────────▼──────────────┐ ┌───────────▼─────────────┐
│      Pure Geo Engine       │ │     Persistence Layer   │
│       (app/geo/*)          │ │       (app/db/*)        │
│  - Zero FastAPI/SQLAlchemy │ │  - SQLAlchemy 2.0 ORM   │
│  - Pure geometric math     │ │  - SQLite foreign keys  │
│  - Pyogrio, Shapely, Pyproj│ │  - Cascading deletes    │
└────────────────────────────┘ └─────────────────────────┘
```

### File-Processing Flow
1. **Request Ingestion**: The HTTP endpoint validates extension (`.zip` or `.kml`) and size ($\le 50\,\text{MB}$). Empty payloads immediately raise `InvalidFileError` (HTTP 400).
2. **Initial DB Record**: Creates an `UploadedFile` record in `PROCESSING` status with a newly assigned UUID and commits immediately.
3. **Disk Persistence & Archive Verification**: Writes content to `storage/{file_id}/{filename}`. For `.zip` archives, runs `safe_extract_zip` (validating every member against zip-slip directory traversal) and verifies that a valid `.shp` exists. If corrupted or missing `.shp`, cleans up the disk directory and DB row, raising `InvalidFileError` (HTTP 400).
4. **Feature Extraction**: Calls `readers.read_features`. If a `.prj` is missing or the file has 0 features, updates status to `FAILED` with an descriptive error message and returns.
5. **Feature Measurement**: Iterates over every extracted `FeatureRecord` and executes `measure()`. Each feature runs inside an isolated `try/except` block to guarantee a single invalid geometry cannot abort processing of remaining features.
6. **Bulk Persistence**: Serializes geometries to GeoJSON strings and maps properties to JSON-compatible dictionaries; bulk-inserts all `Feature` child records into SQLite.
7. **Finalization**: Updates parent file `crs`, `feature_count`, and sets status to `COMPLETED` within a single committed database transaction.

### Measurement Calculation Flow
For each feature geometry:
1. **Empty / Null Guard**: If geometry is `None` or empty, returns status `UNSUPPORTED` with warning `"empty geometry"`.
2. **Flatten 3D to 2D**: Calls `shapely.force_2d(geometry)` to drop elevation ($Z$). Planar measurements are strictly 2-dimensional.
3. **Reprojection to WGS84**: Transforms coordinates to `EPSG:4326` using `pyproj.Transformer(always_xy=True)` if not already in WGS84.
4. **Projected CRS Selection**: Computes the centroid $(X, Y)$ and selects an optimal metric projected CRS (UTM or Polar UPS).
5. **Projected Transformation**: Transforms geometry from `EPSG:4326` into the selected projected coordinate system.
6. **Validation & Repair**: Checks `proj_geom.is_valid`. If invalid, applies `shapely.validation.make_valid()`. If a repaired polygon degenerates into non-polygonal geometries (lines/points), returns `UNSUPPORTED`.
7. **Type-Specific Measurement**:
   - `Polygon` / `MultiPolygon`: Computes `proj_geom.area` in square meters (interior rings/holes subtracted automatically). Status: `OK`.
   - `LineString` / `MultiLineString`: Computes `proj_geom.length` in meters. Status: `OK`.
   - `Point` / `MultiPoint`: Assigns `None` for area and length. Status: `NOT_REQUIRED`.
   - Other types (`GeometryCollection`): Assigns status `UNSUPPORTED`.
8. **Fault Isolation**: Encapsulated in a root `try/except Exception` block returning status `ERROR` with the exception message on unforeseen math errors.

### CRS Handling Strategy
- **Why Never Compute in Degrees?**
  Angular coordinates (`EPSG:4326` longitude and latitude) represent angles on a spheroid, not Euclidean distances. One degree of latitude is approximately 111 km everywhere, but one degree of longitude shrinks from ~111 km at the equator to 0 km at the poles:
  $$\Delta x = \Delta \lambda \cdot \cos(\phi) \cdot 111.32\,\text{km}$$
  Computing Euclidean distance or polygon Shoelace area directly on degrees yields meaningless units ($\text{deg}$ or $\text{deg}^2$) with severe latitude-dependent spatial distortion.
- **UTM Zone Formula**:
  For geometries between latitudes $80^\circ\text{S}$ and $84^\circ\text{N}$, the UTM zone ($1$ to $60$) is derived from the centroid longitude:
  $$\text{zone} = \min\left(60, \max\left(1, \left\lfloor \frac{\text{lon} + 180}{6} \right\rfloor + 1\right)\right)$$
  - Northern hemisphere ($\text{lat} \ge 0^\circ$): `EPSG:326{zone:02d}`
  - Southern hemisphere ($\text{lat} < 0^\circ$): `EPSG:327{zone:02d}`
- **Polar Fallbacks**:
  UTM is mathematically undefined past $84^\circ\text{N}$ and $80^\circ\text{S}$. Universal Polar Stereographic (UPS) projections are used instead:
  - $\text{lat} > 84^\circ\text{N}$: **UPS North** (`EPSG:32661`)
  - $\text{lat} < -80^\circ\text{S}$: **UPS South** (`EPSG:32761`)
- **Axis Order (`always_xy=True`)**:
  WGS84 in EPSG definitions historically specifies $(\text{lat}, \text{lon})$ axis ordering, whereas GIS file formats and Shapely use $(\text{lon}, \text{lat})$ or $(x, y)$. Initializing all transformers with `always_xy=True` forces coordinates to strictly obey $(x, y) = (\text{lon}, \text{lat})$, eliminating coordinate transposition bugs.

---

## 5. Design Decisions and Alternatives

### 1. Synchronous vs Background Processing
- **Decision**: Synchronous processing during the upload HTTP request.
- **Rationale**: For files under the configured limit (50 MB) containing up to tens of thousands of features, synchronous execution keeps the architecture straightforward, eliminating broker dependencies, and returns the finished state immediately to the client.
- **Alternative**: Asynchronous task queues (Celery, RQ, or FastAPI `BackgroundTasks`) writing status updates to the database while returning `202 Accepted`.
- **Practical Tradeoff**: Synchronous processing was chosen deliberately to keep the application deterministic, zero-dependency, and immediately verifiable without requiring external message brokers like Redis or RabbitMQ. For typical inspection workflows (files under 50 MB), synchronous responses provide instant feedback to API clients. In a multi-tenant production environment with multi-gigabyte files or SLA-bound endpoints, moving to an asynchronous queue (e.g. Celery or ARQ) with an event-driven worker pool and polling/webhook notifications would be necessary to avoid blocking HTTP worker threads.

### 2. SQLite vs Postgres / PostGIS
- **Decision**: SQLite via SQLAlchemy 2.0 with strict `PRAGMA foreign_keys=ON`.
- **Rationale**: Completely self-contained with zero external database configuration, allowing anyone to clone and run the application instantly. Geometries are stored as standard GeoJSON text and measurements are calculated in Python via Shapely/Pyproj, avoiding binary database extension requirements.
- **Alternative**: PostgreSQL with PostGIS extension (`ST_Area`, `ST_Length`, `ST_Transform`).
- **Portability & Reviewer Experience**: Using SQLite ensures that reviewers, evaluators, and CI/CD pipelines can clone the repo and run the full test suite and server immediately with `pytest` and `uvicorn`, without installing Docker, running PostgreSQL daemon processes, or compiling C-based PostGIS extensions. For analytical vector workloads of this scale, Shapely 2.0 (backed by GEOS C-library) and Pyproj provide the exact same geometric precision in pure Python memory that PostGIS would in-database.

### 3. UTM vs Equal-Area Local Projections vs Geodesic (`pyproj.Geod`)
- **Decision**: Centroid-based UTM / UPS projection via Pyproj.
- **Rationale**: UTM preserves local conformal shapes and planar distances exceptionally well within its 6° zone. It provides an industry-standard projected CRS identifier (`EPSG:326xx`) stored alongside every feature record.
- **Alternatives**:
  - *Equal-Area projection (e.g., Albers Equal Area / Sinusoidal)*: Better for area calculation across large expanses, but requires dynamically configuring standard parallels per geometry.
  - *Geodesic measurement (`pyproj.Geod.geometry_area_perimeter`)*: Calculates ellipsoidal area directly on spheroidal coordinates without projection, but does not provide a standard projected CRS reference for subsequent GIS mapping.
- **Downstream Interoperability**: Downstream GIS applications (QGIS, ArcGIS, frontend map renderers like Mapbox or OpenLayers, and data pipelines) require known, standard EPSG projection codes (`projected_crs: "EPSG:32644"`) rather than ad-hoc local parameters. Returning a formal EPSG identifier allows clients to re-project, overlay, or verify spatial coordinates against their own layers without guessing what custom projection parameters were applied.

### 4. Per-Feature Error Isolation
- **Decision**: Each feature's measurement is wrapped in its own isolated `try/except` block.
- **Rationale**: In real-world GIS datasets, 99% of features may be valid while one polygon has self-intersections or corrupt coordinates. Crashing the entire file upload due to one bad polygon creates poor user experience. Invalid features are marked with status `ERROR` or `UNSUPPORTED` along with diagnostic warnings, while valid features continue to be measured and stored.

### 5. Storing Measurements at Upload Time vs Recomputing on GET
- **Decision**: Compute and persist measurements during upload; read directly on `GET`.
- **Rationale**: Upload is a one-time operation, while `GET` requests for metadata and measurements can occur repeatedly. Computing measurements upfront allows $O(1)$ indexed reads and fast pagination queries, saving CPU cycles on read endpoints.

### 6. Rejecting Shapefiles Without `.prj` Instead of Guessing
- **Decision**: Rejecting Shapefiles that lack a `.prj` file with status `FAILED` and an explicit error message.
- **Rationale**: While many web files default to WGS84, industrial shapefiles are frequently stored in regional state plane or national coordinate systems without explicit notation. Guessing `EPSG:4326` on a dataset that uses projected meters would yield incorrect coordinates and corrupted measurements. Failing early and loudly is safer than calculating wrong measurements silently.

---

## 6. Known Limitations

1. **Features Spanning Multiple UTM Zones**:
   Geometries extending across multiple 6° UTM zones are projected into the zone of their centroid. While acceptable for localized geometries, continental-scale geometries (e.g. trans-continental rivers or pipelines) will experience scale distortion away from the central meridian.
2. **Special UTM Grid Exceptions**:
   Standard UTM math is applied strictly ($\lfloor(\text{lon} + 180)/6\rfloor + 1$). Regional UTM anomalies such as **Zone 32V** (southwestern Norway) and **Zones 31X, 33X, 35X, 37X** (Svalbard) are not handled.
3. **Large Files and Memory Footprint**:
   Files are read into memory using Pyogrio/GeoPandas and extracted to temporary local disk directories. Datasets exceeding hundreds of megabytes or containing millions of features may experience high memory usage.

---

## 7. Learning and Future Scope

### What Was Learned
- Architecting clean separation between pure domain logic (`app/geo/`) and HTTP/ORM frameworks.
- Deepening knowledge of coordinate reference system transformations, axis-ordering hazards (`always_xy=True`), and ellipsoidal geometry principles.
- Robust file ingestion practices including preventing zip-slip path traversal and sanitizing non-standard property values across shapefile and KML layers.
- SQLAlchemy 2.0 type-safe mappings and SQLite foreign key constraints.
- Navigating OGR/pyogrio multi-layer representations in KML files, where folders within a KML file are parsed as distinct layers, requiring dynamic layer enumeration and continuous feature index tracking across layers.
- Managing coordinate axis inversion traps (`always_xy=True`) when translating geographic geometries into projected planar CRS, and ensuring invalid geometries are gracefully repaired (`shapely.validation.make_valid`) without crashing the ingestion transaction.

### Future Enhancements
- **Asynchronous Task Queue**: Integrate Redis and Celery (or ARQ) to process multi-gigabyte uploads asynchronously with progress webhooks.
- **Spatial Indexing & PostGIS**: Migrate to PostgreSQL with PostGIS using `GIST` spatial indexes to support spatial queries (`ST_Intersects`, bounding box filtering).
- **Format Expansion**: Add support for GeoJSON, GeoPackage (`.gpkg`), and flat geobuf files.
- **Streaming Geometry Parser**: Implement chunked streaming feature ingestion using OGR/Pyogrio generators to handle files of arbitrary size with constant memory overhead.
- **Custom CRS Override**: Allow API clients to provide an optional override CRS in the upload request for legacy Shapefiles lacking `.prj` files.
- **Direct GeoTIFF / Raster Analysis**: Extend the API to accept raster elevation and multispectral datasets (e.g., via Rasterio) to calculate surface metrics, zonal statistics, and polygon elevation profiles alongside vector measurements.
