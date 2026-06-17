"""
Microsoft Global ML Building Footprints loader for Karrada, Baghdad.

The MS dataset is split by Bing Maps quadkey at zoom level 9. We compute
which tile(s) cover the Karrada AOI, download only those, stream-filter to
the AOI bbox, and save a clipped GeoJSON. All of Karrada falls in tile
122113313 (~120 MB compressed, one-time download).

Usage (one-time setup):
    python -m nova.footprints          # downloads + clips + prints stats
    nova-footprints                     # same via installed script

After setup, call load_karrada_footprints() from other modules.
"""

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

# Karrada peninsula, central Baghdad  [west, south, east, north]
KARRADA_BBOX = [44.385, 33.285, 44.430, 33.320]

DATA_DIR = Path(__file__).parent.parent / "data" / "footprints"
CLIPPED_PATH = DATA_DIR / "karrada.geojson"

_DATASET_CSV_URL = (
    "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"
)
_QUADKEY_ZOOM = 9


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


def _karrada_quadkeys(zoom: int = _QUADKEY_ZOOM) -> set[str]:
    """Compute the set of quadkeys that cover the Karrada AOI bbox."""
    W, S, E, N = KARRADA_BBOX
    # Sample bbox corners and midpoints to catch tile boundaries
    return {
        _lat_lon_to_quadkey(lat, lon, zoom)
        for lat in [S, (S + N) / 2, N]
        for lon in [W, (W + E) / 2, E]
    }


# ---------------------------------------------------------------------------
# Tile discovery
# ---------------------------------------------------------------------------


def _get_karrada_tile_urls() -> list[str]:
    """Fetch the MS dataset CSV and return URLs for tiles covering Karrada."""
    print(f"  fetching tile index from MS Building Footprints...")
    with httpx.Client(timeout=30) as client:
        r = client.get(_DATASET_CSV_URL)
        r.raise_for_status()

    relevant_qks = _karrada_quadkeys()
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


def _stream_tile_features(url: str, label: str) -> list[dict]:
    """
    Download one .csv.gz tile (content is GeoJSONL despite the extension),
    stream-filter to the Karrada AOI bbox, return matching GeoJSON features.
    """
    W, S, E, N = KARRADA_BBOX
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


def load_karrada_footprints() -> gpd.GeoDataFrame:
    """Load the pre-clipped Karrada building footprints GeoDataFrame (EPSG:4326).

    Raises FileNotFoundError if the one-time setup hasn't been run.
    Run: python -m nova.footprints
    """
    if not CLIPPED_PATH.exists():
        raise FileNotFoundError(
            f"Karrada footprints not found at {CLIPPED_PATH}.\n"
            "Run: python -m nova.footprints"
        )
    return gpd.read_file(CLIPPED_PATH)


def setup_karrada_footprints() -> gpd.GeoDataFrame:
    """
    One-time setup: find the relevant MS Building Footprints tile(s),
    download them, filter to Karrada, and save karrada.geojson.

    Skips the download if karrada.geojson already exists.
    """
    if CLIPPED_PATH.exists():
        size_kb = CLIPPED_PATH.stat().st_size / 1e3
        print(f"  footprints already set up ({size_kb:.0f} KB): {CLIPPED_PATH}")
        return load_karrada_footprints()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    tile_urls = _get_karrada_tile_urls()
    if not tile_urls:
        sys.exit(
            "No tiles found covering Karrada AOI in the MS dataset CSV.\n"
            f"Expected quadkeys: {_karrada_quadkeys()}\n"
            f"CSV URL: {_DATASET_CSV_URL}"
        )
    print(f"  {len(tile_urls)} tile(s) cover Karrada")

    all_features: list[dict] = []
    for i, url in enumerate(tile_urls, 1):
        qk_label = url.split("quadkey=")[-1].split("/")[0] if "quadkey=" in url else str(i)
        all_features.extend(_stream_tile_features(url, f"{qk_label} ({i}/{len(tile_urls)})"))

    if not all_features:
        sys.exit(
            "No footprints found in Karrada bbox. "
            f"Check bbox {KARRADA_BBOX} is correct."
        )

    gdf = gpd.GeoDataFrame.from_features(all_features, crs="EPSG:4326")
    gdf = gdf.clip(shapely_box(*KARRADA_BBOX))

    gdf.to_file(CLIPPED_PATH, driver="GeoJSON")
    print(f"  saved → {CLIPPED_PATH}  ({CLIPPED_PATH.stat().st_size/1e3:.0f} KB)")
    return gdf


def _print_stats(gdf: gpd.GeoDataFrame) -> None:
    utm = gdf.to_crs("EPSG:32638")  # UTM zone 38N — accurate metric CRS for Iraq
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
    print("=== Microsoft Building Footprints — Karrada setup ===\n")

    print("Step 1: Download and clip footprints")
    gdf = setup_karrada_footprints()

    print("\nStep 2: Summary stats")
    _print_stats(gdf)

    print(f"\nDone. Footprints ready at: {CLIPPED_PATH.resolve()}")


if __name__ == "__main__":
    main()
