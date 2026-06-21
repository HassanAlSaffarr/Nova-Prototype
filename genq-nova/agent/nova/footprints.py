"""
Microsoft Global ML Building Footprints loader, per AOI.

The MS dataset is split by Bing Maps quadkey at zoom level 9. We compute
which tile(s) cover an AOI bbox, download only those, stream-filter to the
bbox, and save a clipped GeoJSON (one ~120 MB compressed tile per download).

Usage (one-time setup, per AOI):
    python -m nova.footprints --aoi karrada
    python -m nova.footprints --aoi bismayah

After setup, call load_footprints(aoi) from other modules.
"""

import argparse
import csv
import gzip
import io
import json
import math
import sys
from pathlib import Path

import geopandas as gpd
import httpx
from shapely.geometry import box as shapely_box
from shapely.geometry import shape

from nova.config import AOI_PRESETS, CRS_UTM, DATA_DIR as _DATA_DIR

DATA_DIR = _DATA_DIR / "footprints"
CLIPPED_PATH = DATA_DIR / "karrada.geojson"  # back-compat default

_DATASET_CSV_URL = (
    "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"
)
_QUADKEY_ZOOM = 9


def _clipped_path(aoi: str) -> Path:
    return DATA_DIR / f"{aoi}.geojson"


# ---------------------------------------------------------------------------
# Quadkey helpers
# ---------------------------------------------------------------------------


def _lat_lon_to_quadkey(lat: float, lon: float, zoom: int) -> str:
    """Convert WGS84 lat/lon to Bing Maps quadkey string at given zoom level."""
    sin_lat = math.sin(lat * math.pi / 180)
    n = 2 ** zoom
    tile_x = min(int(((lon + 180) / 360) * n), n - 1)
    pixel_y = (
        0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)
    ) * n * 256
    tile_y = min(int(pixel_y / 256), n - 1)

    qk = ""
    for i in range(zoom, 0, -1):
        d = 0
        mask = 1 << (i - 1)
        if tile_x & mask:
            d += 1
        if tile_y & mask:
            d += 2
        qk += str(d)
    return qk


def _quadkeys_overlap(qk_tile: str, qk_target: str) -> bool:
    """True if a tile quadkey overlaps the target (one is a prefix of the other)."""
    return qk_tile.startswith(qk_target) or qk_target.startswith(qk_tile)


def _aoi_quadkeys(bbox: list[float], zoom: int = _QUADKEY_ZOOM) -> set[str]:
    """Compute the set of quadkeys that cover an AOI bbox [W,S,E,N]."""
    W, S, E, N = bbox
    # Sample bbox corners and midpoints to catch tile boundaries
    return {
        _lat_lon_to_quadkey(lat, lon, zoom)
        for lat in [S, (S + N) / 2, N]
        for lon in [W, (W + E) / 2, E]
    }


# ---------------------------------------------------------------------------
# Tile discovery
# ---------------------------------------------------------------------------


def _get_tile_urls(bbox: list[float]) -> list[str]:
    """Fetch the MS dataset CSV and return URLs for tiles covering the bbox."""
    print(f"  fetching tile index from MS Building Footprints...")
    with httpx.Client(timeout=30) as client:
        r = client.get(_DATASET_CSV_URL)
        r.raise_for_status()

    relevant_qks = _aoi_quadkeys(bbox)
    reader = csv.DictReader(io.StringIO(r.text))
    urls: list[str] = []

    for row in reader:
        if row.get("Location", "").strip().lower() != "iraq":
            continue
        qk = row.get("QuadKey", "").strip()
        url = row.get("Url", "").strip().strip('"')
        if url and any(_quadkeys_overlap(qk, rqk) for rqk in relevant_qks):
            urls.append(url)

    return urls


# ---------------------------------------------------------------------------
# Download + filter
# ---------------------------------------------------------------------------


def _stream_tile_features(url: str, label: str, bbox: list[float]) -> list[dict]:
    """
    Download one .csv.gz tile (content is GeoJSONL despite the extension),
    stream-filter to the AOI bbox, return matching GeoJSON features.
    """
    W, S, E, N = bbox
    karrada_box = shapely_box(W, S, E, N)

    print(f"  downloading tile {label}  (may take ~10-30s)...")
    with httpx.Client(timeout=300, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()

    total_mb = len(r.content) / 1e6
    print(f"  {total_mb:.1f} MB downloaded — streaming features...")

    features: list[dict] = []
    scanned = 0

    with gzip.open(io.BytesIO(r.content), "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                feat = json.loads(line)
            except json.JSONDecodeError:
                continue

            scanned += 1
            geom_dict = feat.get("geometry", {})
            geom_type = geom_dict.get("type", "")
            coords = geom_dict.get("coordinates")
            if not coords:
                continue

            # Fast bbox pre-filter on raw coordinates
            outer = (
                coords[0]
                if geom_type == "Polygon"
                else (coords[0][0] if geom_type == "MultiPolygon" else None)
            )
            if outer is None:
                continue

            xs = [c[0] for c in outer]
            ys = [c[1] for c in outer]
            if max(xs) < W or min(xs) > E or max(ys) < S or min(ys) > N:
                continue

            if shape(geom_dict).intersects(karrada_box):
                features.append(feat)

            if scanned % 200_000 == 0:
                print(f"  scanned {scanned//1000}k features, {len(features)} in AOI...", end="\r")

    print(f"  scanned {scanned:,} features → {len(features)} in Karrada bbox   ")
    return features


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_footprints(aoi: str = "karrada") -> gpd.GeoDataFrame:
    """Load the pre-clipped building footprints for an AOI (EPSG:4326)."""
    path = _clipped_path(aoi)
    if not path.exists():
        raise FileNotFoundError(
            f"{aoi} footprints not found at {path}.\n"
            f"Run: python -m nova.footprints --aoi {aoi}"
        )
    return gpd.read_file(path)


# Back-compat alias.
def load_karrada_footprints() -> gpd.GeoDataFrame:
    return load_footprints("karrada")


def setup_footprints(aoi: str = "karrada") -> gpd.GeoDataFrame:
    """
    One-time setup for an AOI: find the MS Building Footprints tile(s) covering
    its bbox, download, stream-filter to the bbox, and save <aoi>.geojson.
    """
    bbox = AOI_PRESETS[aoi]
    path = _clipped_path(aoi)
    if path.exists():
        size_kb = path.stat().st_size / 1e3
        print(f"  footprints already set up ({size_kb:.0f} KB): {path}")
        return load_footprints(aoi)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    tile_urls = _get_tile_urls(bbox)
    if not tile_urls:
        sys.exit(
            f"No tiles found covering {aoi} AOI.\n"
            f"Expected quadkeys: {_aoi_quadkeys(bbox)}\n"
            f"CSV URL: {_DATASET_CSV_URL}"
        )
    print(f"  {len(tile_urls)} tile(s) cover {aoi}")

    all_features: list[dict] = []
    for i, url in enumerate(tile_urls, 1):
        qk_label = url.split("quadkey=")[-1].split("/")[0] if "quadkey=" in url else str(i)
        all_features.extend(
            _stream_tile_features(url, f"{qk_label} ({i}/{len(tile_urls)})", bbox)
        )

    if not all_features:
        sys.exit(f"No footprints found in {aoi} bbox {bbox}.")

    gdf = gpd.GeoDataFrame.from_features(all_features, crs="EPSG:4326")
    gdf = gdf.clip(shapely_box(*bbox))

    gdf.to_file(path, driver="GeoJSON")
    print(f"  saved → {path}  ({path.stat().st_size/1e3:.0f} KB)")
    return gdf


def _print_stats(gdf: gpd.GeoDataFrame) -> None:
    utm = gdf.to_crs(CRS_UTM)
    utm["area_m2"] = utm.geometry.area
    total_ha = utm["area_m2"].sum() / 1e4
    print(f"  footprints     : {len(gdf):,}")
    print(f"  total area     : {total_ha:.2f} ha")
    print(f"  mean area      : {utm['area_m2'].mean():.1f} m²")
    print(f"  median area    : {utm['area_m2'].median():.1f} m²")
    print(f"  95th pct area  : {utm['area_m2'].quantile(0.95):.1f} m²")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(prog="nova-footprints")
    parser.add_argument("--aoi", default="karrada", choices=list(AOI_PRESETS),
                        help="AOI preset (default: karrada)")
    args = parser.parse_args()

    print(f"=== Microsoft Building Footprints — {args.aoi} setup ===\n")
    print("Step 1: Download and clip footprints")
    gdf = setup_footprints(args.aoi)

    print("\nStep 2: Summary stats")
    _print_stats(gdf)

    print(f"\nDone. Footprints ready at: {_clipped_path(args.aoi).resolve()}")


if __name__ == "__main__":
    main()
