"""
Microsoft Global ML Building Footprints loader for Karrada, Baghdad.

Usage (one-time setup):
    python -m nova.footprints          # downloads + clips + prints stats
    nova-footprints                     # same via installed script

After setup, call load_karrada_footprints() from other modules.
"""

import csv
import gzip
import io
import json
import sys
from pathlib import Path

import geopandas as gpd
import httpx
from shapely.geometry import box as shapely_box
from shapely.geometry import shape

# Karrada peninsula, central Baghdad  [west, south, east, north]
KARRADA_BBOX = [44.385, 33.285, 44.430, 33.320]

DATA_DIR = Path(__file__).parent.parent / "data" / "footprints"
RAW_PATH = DATA_DIR / "iraq_raw.geojsonl.gz"
CLIPPED_PATH = DATA_DIR / "karrada.geojson"

_DATASET_LINKS_URL = (
    "https://raw.githubusercontent.com/microsoft/GlobalMLBuildingFootprints"
    "/main/dataset-links.csv"
)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def _get_iraq_urls() -> list[str]:
    """Fetch the MS dataset-links CSV and return all Iraq download URLs."""
    with httpx.Client(timeout=30) as client:
        r = client.get(_DATASET_LINKS_URL)
        r.raise_for_status()

    reader = csv.DictReader(io.StringIO(r.text))
    urls: list[str] = []
    for row in reader:
        location = next(
            (v for k, v in row.items() if k.lower() == "location"), ""
        )
        url = next(
            (v for k, v in row.items() if k.lower() == "url"), ""
        ).strip().strip('"')
        if "iraq" in location.lower() and url.startswith("https://"):
            urls.append(url)

    if not urls:
        # Fallback: scan all cells for anything that looks like an Iraq URL
        for row in csv.reader(io.StringIO(r.text)):
            if any("iraq" in cell.lower() for cell in row):
                for cell in row:
                    cell = cell.strip().strip('"')
                    if cell.startswith("https://") and "geojsonl" in cell:
                        urls.append(cell)

    return list(dict.fromkeys(urls))  # deduplicate, preserve order


def download_iraq_footprints() -> None:
    """Download the Iraq building footprints file (cached — skips if present)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if RAW_PATH.exists():
        size_mb = RAW_PATH.stat().st_size / 1e6
        print(f"  raw file already cached ({size_mb:.1f} MB): {RAW_PATH}")
        return

    print("  fetching dataset index from GitHub...")
    urls = _get_iraq_urls()
    if not urls:
        sys.exit(
            "Could not find Iraq URL in MS dataset-links.csv.\n"
            "Check: https://github.com/microsoft/GlobalMLBuildingFootprints"
        )

    if len(urls) > 1:
        print(f"  found {len(urls)} Iraq tile(s) — will download all and merge")

    all_bytes = b""
    for i, url in enumerate(urls, 1):
        label = f"tile {i}/{len(urls)}" if len(urls) > 1 else "Iraq footprints"
        print(f"  downloading {label}: {url}")
        with httpx.stream("GET", url, timeout=600, follow_redirects=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            chunks = []
            for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                chunks.append(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    mb = downloaded / 1e6
                    print(f"  {pct:5.1f}%  {mb:.0f} / {total/1e6:.0f} MB", end="\r")
            all_bytes += b"".join(chunks)
        print()  # newline after \r progress

    RAW_PATH.write_bytes(all_bytes)
    print(f"  saved → {RAW_PATH}  ({RAW_PATH.stat().st_size/1e6:.1f} MB)")


# ---------------------------------------------------------------------------
# Clip
# ---------------------------------------------------------------------------


def clip_to_karrada() -> gpd.GeoDataFrame:
    """
    Stream the Iraq GeoJSONL, filter to the Karrada AOI bbox, save clipped GeoJSON.
    Uses a fast coordinate pre-filter before the full shapely intersection check.
    """
    W, S, E, N = KARRADA_BBOX
    karrada_box = shapely_box(W, S, E, N)
    features: list[dict] = []

    print(f"  streaming {RAW_PATH.name} and filtering to Karrada bbox...")
    with gzip.open(RAW_PATH, "rt", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                feat = json.loads(line)
            except json.JSONDecodeError:
                continue

            geom_dict = feat.get("geometry", {})
            coords = geom_dict.get("coordinates")
            if not coords:
                continue

            # Fast bbox pre-filter on raw coordinates (avoids shapely object creation
            # for the vast majority of features that are nowhere near the AOI)
            geom_type = geom_dict.get("type", "")
            if geom_type == "Polygon":
                outer = coords[0]
            elif geom_type == "MultiPolygon":
                outer = coords[0][0]
            else:
                continue

            xs = [c[0] for c in outer]
            ys = [c[1] for c in outer]
            if max(xs) < W or min(xs) > E or max(ys) < S or min(ys) > N:
                continue  # bbox doesn't overlap — skip

            # Full intersection check for the small fraction that pass the bbox test
            if shape(geom_dict).intersects(karrada_box):
                features.append(feat)

            if (i + 1) % 500_000 == 0:
                scanned_m = (i + 1) / 1_000_000
                print(f"  {scanned_m:.1f}M features scanned, {len(features)} in AOI...", end="\r")

    print(f"\n  found {len(features):,} footprints intersecting Karrada bbox")

    if not features:
        sys.exit(
            "No footprints found. Check that the Iraq tile covers the Karrada AOI "
            f"(bbox: {KARRADA_BBOX}). The raw file may be for a different region."
        )

    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    gdf = gdf.clip(karrada_box)  # exact clip to AOI boundary

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    gdf.to_file(CLIPPED_PATH, driver="GeoJSON")
    print(f"  saved → {CLIPPED_PATH}")
    return gdf


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_karrada_footprints() -> gpd.GeoDataFrame:
    """Load the pre-clipped Karrada building footprints GeoDataFrame (EPSG:4326).

    Raises FileNotFoundError if the one-time setup hasn't been run yet.
    Run `python -m nova.footprints` to set up.
    """
    if not CLIPPED_PATH.exists():
        raise FileNotFoundError(
            f"Karrada footprints not found at {CLIPPED_PATH}.\n"
            "Run: python -m nova.footprints"
        )
    return gpd.read_file(CLIPPED_PATH)


def _print_stats(gdf: gpd.GeoDataFrame) -> None:
    utm = gdf.to_crs("EPSG:32638")  # UTM zone 38N — accurate for Iraq
    utm["area_m2"] = utm.geometry.area
    total_area_ha = utm["area_m2"].sum() / 1e4
    mean_m2 = utm["area_m2"].mean()
    median_m2 = utm["area_m2"].median()
    p95_m2 = utm["area_m2"].quantile(0.95)
    print(f"  footprints     : {len(gdf):,}")
    print(f"  total area     : {total_area_ha:.2f} ha")
    print(f"  mean area      : {mean_m2:.1f} m²")
    print(f"  median area    : {median_m2:.1f} m²")
    print(f"  95th pct area  : {p95_m2:.1f} m²")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    print("=== Microsoft Building Footprints — Karrada setup ===\n")

    print("Step 1: Download Iraq footprints")
    download_iraq_footprints()

    print("\nStep 2: Clip to Karrada AOI")
    gdf = clip_to_karrada()

    print("\nStep 3: Summary stats")
    _print_stats(gdf)

    print(f"\nDone. Footprints ready at: {CLIPPED_PATH.resolve()}")


if __name__ == "__main__":
    main()
