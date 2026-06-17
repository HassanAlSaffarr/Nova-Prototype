"""
Sentinel-2 raster-based change detection for a single AOI.

Core function: detect_changes(aoi_bounds, date_before, date_after) → GeoDataFrame

Approach:
  1. Build cloud-free median composites from COPERNICUS/S2_SR_HARMONIZED
     for a "before" and "after" window (each ~3 months).
  2. Compute NDVI and NDBI for each composite.
  3. Subtract to get ΔNDVI, ΔNDBI, Δbrightness; also carry an MNDWI-based
     WATER band so the Tigris can be masked.
  4. Download the 4-band diff raster from GEE (cached to data/rasters/).
  5. Threshold: ΔNDVI < ndvi_threshold AND ΔNDBI > ndbi_threshold,
     excluding open-water pixels → pixels where vegetation/bare soil was
     replaced by built surface.
  6. Vectorise contiguous flagged regions with rasterio.features.shapes().
  7. Filter polygons below min_area_m2.
  8. Sample raster at polygon centroids for per-detection delta values.
  9. Return WGS84 GeoDataFrame.

Assumes ee.Initialize() has already been called by the caller.
"""

import io
import zipfile
from pathlib import Path

import ee
import geopandas as gpd
import httpx
import numpy as np
import rasterio
import rasterio.features
from rasterio.io import MemoryFile
from shapely.geometry import shape

from nova.config import CRS_UTM, DATA_DIR

CACHE_DIR = DATA_DIR / "rasters"

# Construction signature thresholds (tunable via detect_changes() args)
_DEFAULT_NDVI_THRESH = -0.10  # ΔNDVI must drop by at least this much
_DEFAULT_NDBI_THRESH = 0.10   # ΔNDBI must rise by at least this much
_DEFAULT_MIN_AREA = 1000.0    # m² — tuned: below this is noise / blankets the AOI
_WATER_THRESH = 0.0           # MNDWI > this in either epoch ⇒ open water, masked out


# ---------------------------------------------------------------------------
# GEE composite helpers
# ---------------------------------------------------------------------------


def _add_indices(img: ee.Image) -> ee.Image:
    """Add NDVI, NDBI, MNDWI, and visible-mean brightness bands to an S2 image."""
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndbi = img.normalizedDifference(["B11", "B8"]).rename("NDBI")
    # MNDWI = (Green - SWIR) / (Green + SWIR); > 0 ≈ open water (the Tigris)
    mndwi = img.normalizedDifference(["B3", "B11"]).rename("MNDWI")
    brightness = (
        img.select(["B4", "B3", "B2"]).reduce(ee.Reducer.mean()).rename("BRIGHTNESS")
    )
    return img.addBands([ndvi, ndbi, mndwi, brightness])


def _build_composite(
    aoi: ee.Geometry,
    date_start: str,
    date_end: str,
    cloud_max: int,
) -> ee.Image:
    """Return median S2 composite with NDVI, NDBI, BRIGHTNESS bands."""
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(date_start, date_end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_max))
        .map(_add_indices)
    )
    n = collection.size().getInfo()
    print(f"    {date_start}→{date_end}: {n} scenes (cloud < {cloud_max}%)")

    if n == 0 and cloud_max < 40:
        print(f"    No scenes — retrying with cloud < 40%...")
        collection = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(aoi)
            .filterDate(date_start, date_end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40))
            .map(_add_indices)
        )
        n = collection.size().getInfo()
        print(f"    retry: {n} scenes")

    if n == 0:
        raise RuntimeError(
            f"No S2 scenes found for {date_start}→{date_end}. "
            "Try widening the date window."
        )

    return collection.select(["NDVI", "NDBI", "MNDWI", "BRIGHTNESS"]).median()


# ---------------------------------------------------------------------------
# GEE raster download (cached)
# ---------------------------------------------------------------------------


def _download_diff_raster(
    aoi: ee.Geometry,
    date_before: tuple[str, str],
    date_after: tuple[str, str],
    cloud_max: int,
    cache_stem: str,
) -> Path:
    """
    Build before/after composites in GEE, subtract them, download the 4-band
    diff raster as a UTM GeoTIFF.

    Bands in returned TIF (in order):
        1: DELTA_NDVI
        2: DELTA_NDBI
        3: DELTA_BRIGHTNESS
        4: WATER          — max(MNDWI_before, MNDWI_after); > 0 ≈ open water,
                            used to mask out Tigris pixels before vectorising
    """
    cache_path = CACHE_DIR / f"{cache_stem}.tif"
    if cache_path.exists():
        print(f"  diff raster cached: {cache_path.name}")
        return cache_path

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print("  building before composite...")
    before = _build_composite(aoi, date_before[0], date_before[1], cloud_max)

    print("  building after composite...")
    after = _build_composite(aoi, date_after[0], date_after[1], cloud_max)

    diff = (
        after.select(["NDVI", "NDBI", "BRIGHTNESS"])
        .subtract(before.select(["NDVI", "NDBI", "BRIGHTNESS"]))
        .rename(["DELTA_NDVI", "DELTA_NDBI", "DELTA_BRIGHTNESS"])
    )
    # Water indicator: a pixel that is water in EITHER epoch should be masked,
    # since index "changes" over the river are meaningless (level/turbidity).
    water = before.select("MNDWI").max(after.select("MNDWI")).rename("WATER")
    diff = diff.addBands(water)

    bands = ["DELTA_NDVI", "DELTA_NDBI", "DELTA_BRIGHTNESS", "WATER"]

    print("  requesting download URL from GEE...")
    url = diff.getDownloadURL(
        {
            "scale": 10,
            "crs": CRS_UTM,
            "region": aoi,
            "format": "GEO_TIFF",
            "bands": bands,
        }
    )

    print("  downloading diff raster...")
    with httpx.Client(timeout=300, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()

    content = r.content

    if content[:2] == b"PK":
        # GEE returned a zip of per-band TIFs
        _merge_zip_to_tif(content, bands, cache_path)
    else:
        cache_path.write_bytes(content)

    print(f"  saved → {cache_path.name}  ({cache_path.stat().st_size/1e3:.0f} KB)")
    return cache_path


def _merge_zip_to_tif(
    zip_bytes: bytes,
    band_order: list[str],
    out_path: Path,
) -> None:
    """
    Merge per-band TIFs from a GEE zip into a single multi-band GeoTIFF.
    GEE names files as '{prefix}.{band_name}.tif' or just '{band_name}.tif'.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # Map stem suffix → raw bytes for each TIF in the zip
        tif_map: dict[str, bytes] = {}
        for name in zf.namelist():
            if not name.endswith(".tif"):
                continue
            stem = Path(name).stem        # e.g. "download.DELTA_NDVI"
            key = stem.split(".")[-1]     # → "DELTA_NDVI"
            tif_map[key] = zf.read(name)

    arrays = []
    profile = None
    for band in band_order:
        data = tif_map.get(band)
        if data is None:
            # Fallback: positional order
            idx = band_order.index(band)
            data = list(tif_map.values())[idx]
        with MemoryFile(data) as mf:
            with mf.open() as src:
                arrays.append(src.read(1))
                if profile is None:
                    profile = src.profile.copy()

    profile.update(count=len(arrays))
    with rasterio.open(out_path, "w", **profile) as dst:
        for i, arr in enumerate(arrays, 1):
            dst.write(arr, i)


# ---------------------------------------------------------------------------
# Vectorise + attribute
# ---------------------------------------------------------------------------


def _vectorise(
    tif_path: Path,
    ndvi_thresh: float,
    ndbi_thresh: float,
) -> tuple[list, dict, rasterio.CRS]:
    """
    Read the diff raster, apply construction threshold, vectorise contiguous
    regions. Returns (geometries_list, stats_dict, crs).

    stats_dict keys: 'delta_ndvi', 'delta_ndbi', 'delta_brightness'
    Each value is a list aligned with geometries_list.
    """
    with rasterio.open(tif_path) as src:
        d_ndvi = src.read(1).astype(np.float32)
        d_ndbi = src.read(2).astype(np.float32)
        d_bright = src.read(3).astype(np.float32)
        water = src.read(4).astype(np.float32)
        transform = src.transform
        crs = src.crs
        nodata = src.nodata

    # Mask nodata pixels
    nodata_mask = np.zeros(d_ndvi.shape, dtype=bool)
    if nodata is not None:
        nodata_mask |= d_ndvi == nodata
    nodata_mask |= np.isnan(d_ndvi) | np.isnan(d_ndbi)

    # Water mask: MNDWI > 0 in either epoch → Tigris / open water. Exclude it,
    # otherwise seasonal level/turbidity shifts masquerade as construction.
    water_mask = (water > _WATER_THRESH) | np.isnan(water)

    # Construction mask: vegetation/bare soil → built surface, on dry land only
    construction = (
        (d_ndvi < ndvi_thresh)
        & (d_ndbi > ndbi_thresh)
        & ~nodata_mask
        & ~water_mask
    ).astype(np.uint8)

    # Vectorise contiguous regions
    shapes_iter = rasterio.features.shapes(
        construction,
        mask=construction,
        transform=transform,
        connectivity=8,
    )

    geoms = []
    stats: dict[str, list] = {
        "delta_ndvi": [],
        "delta_ndbi": [],
        "delta_brightness": [],
    }

    for geom_dict, _ in shapes_iter:
        poly = shape(geom_dict)
        centroid = poly.centroid
        # Sample raster values at centroid pixel
        row, col = rasterio.transform.rowcol(transform, centroid.x, centroid.y)
        row = int(np.clip(row, 0, d_ndvi.shape[0] - 1))
        col = int(np.clip(col, 0, d_ndvi.shape[1] - 1))
        geoms.append(poly)
        stats["delta_ndvi"].append(float(d_ndvi[row, col]))
        stats["delta_ndbi"].append(float(d_ndbi[row, col]))
        stats["delta_brightness"].append(float(d_bright[row, col]))

    return geoms, stats, crs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_changes(
    aoi_bounds: list[float],
    date_before: tuple[str, str],
    date_after: tuple[str, str],
    cloud_threshold: int = 20,
    ndvi_threshold: float = _DEFAULT_NDVI_THRESH,
    ndbi_threshold: float = _DEFAULT_NDBI_THRESH,
    min_area_m2: float = _DEFAULT_MIN_AREA,
) -> gpd.GeoDataFrame:
    """
    Detect likely construction events between two date windows over an AOI.

    Parameters
    ----------
    aoi_bounds      : [west, south, east, north] in WGS84 degrees
    date_before     : (start, end) for the reference composite, e.g. ('2022-06-01', '2022-09-01')
    date_after      : (start, end) for the changed composite, e.g. ('2024-06-01', '2024-09-01')
    cloud_threshold : max CLOUDY_PIXEL_PERCENTAGE per S2 scene
    ndvi_threshold  : ΔNDVI must be ≤ this (negative = vegetation loss)
    ndbi_threshold  : ΔNDBI must be ≥ this (positive = more built surface)
    min_area_m2     : minimum polygon area to keep (smaller = noise)

    Returns
    -------
    GeoDataFrame with columns:
        geometry, delta_ndvi, delta_ndbi, delta_brightness,
        area_m2, centroid_lat, centroid_lon, date_after (end of after window)
    CRS: EPSG:4326
    """
    aoi_ee = ee.Geometry.Rectangle(aoi_bounds)

    # Cache key encodes the full parameters so different runs don't collide
    before_tag = f"{date_before[0]}_{date_before[1]}".replace("-", "")
    after_tag = f"{date_after[0]}_{date_after[1]}".replace("-", "")
    # "_w" schema marker: 4-band raster incl. WATER (bump if band layout changes)
    cache_stem = f"diff_{before_tag}_vs_{after_tag}_c{cloud_threshold}_w"

    tif_path = _download_diff_raster(
        aoi_ee, date_before, date_after, cloud_threshold, cache_stem
    )

    print(f"  vectorising (ΔNDVI<{ndvi_threshold}, ΔNDBI>{ndbi_threshold})...")
    geoms, stats, utm_crs = _vectorise(tif_path, ndvi_threshold, ndbi_threshold)
    print(f"  raw polygons before area filter: {len(geoms)}")

    if not geoms:
        print(
            "  WARNING: no construction pixels found. "
            f"Try loosening thresholds (current: ΔNDVI<{ndvi_threshold}, ΔNDBI>{ndbi_threshold})"
        )
        return gpd.GeoDataFrame(
            columns=[
                "geometry", "delta_ndvi", "delta_ndbi", "delta_brightness",
                "area_m2", "centroid_lat", "centroid_lon", "date_after",
            ],
            crs="EPSG:4326",
        )

    gdf_utm = gpd.GeoDataFrame(
        {
            "geometry": geoms,
            **stats,
        },
        crs=utm_crs,
    )

    # Filter by area
    gdf_utm["area_m2"] = gdf_utm.geometry.area
    gdf_utm = gdf_utm[gdf_utm["area_m2"] >= min_area_m2].copy()
    print(f"  polygons after area filter (≥{min_area_m2} m²): {len(gdf_utm)}")

    # Compute centroids in the projected (UTM) CRS for accuracy, then reproject.
    centroids = gdf_utm.geometry.centroid.to_crs("EPSG:4326")
    gdf = gdf_utm.to_crs("EPSG:4326")
    gdf["centroid_lat"] = centroids.y
    gdf["centroid_lon"] = centroids.x
    gdf["date_after"] = date_after[1]

    return gdf
