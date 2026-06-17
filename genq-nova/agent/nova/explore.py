"""
Pull a cloud-free Sentinel-2 composite of Karrada (Baghdad) via GEE
and save a preview PNG to agent/data/preview_karrada.png.

Run once to confirm the AOI bounding box is correct before building
the change-detection loop.

Prerequisites:
  1. GEE access approved at https://earthengine.google.com
  2. `earthengine authenticate` run once in the terminal
  3. GEE_PROJECT env var set to your Google Cloud project ID
"""

import os
import sys

import ee
import httpx

from nova.config import DATA_DIR, KARRADA_BBOX as AOI_BOUNDS

DATE_START = "2024-01-01"
DATE_END = "2024-04-01"
MAX_CLOUD_PCT = 20  # CLOUDY_PIXEL_PERCENTAGE threshold

OUTPUT_PATH = DATA_DIR / "preview_karrada.png"


def build_composite() -> ee.Image:
    aoi = ee.Geometry.Rectangle(AOI_BOUNDS)
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(DATE_START, DATE_END)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD_PCT))
    )
    n = collection.size().getInfo()
    print(f"  scenes found in AOI: {n}")
    if n == 0:
        sys.exit(
            "No images found — try widening the date range or raising MAX_CLOUD_PCT"
        )
    return collection.median().clip(aoi)


def save_preview(image: ee.Image) -> None:
    aoi = ee.Geometry.Rectangle(AOI_BOUNDS)
    # True-colour RGB: B4=Red, B3=Green, B2=Blue
    # S2 SR surface reflectance values scale 0–10000; 3000 ≈ bright urban
    url = image.getThumbURL(
        {
            "min": 0,
            "max": 3000,
            "bands": ["B4", "B3", "B2"],
            "region": aoi,
            "dimensions": 1024,
            "format": "png",
        }
    )
    print(f"  fetching thumbnail from GEE...")
    with httpx.Client(timeout=120) as client:
        r = client.get(url)
        r.raise_for_status()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(r.content)
    print(f"  saved → {OUTPUT_PATH}")


def main() -> None:
    project = os.environ.get("GEE_PROJECT")
    if not project:
        sys.exit(
            "GEE_PROJECT is not set.\n"
            "Export your Google Cloud project ID, e.g.:\n"
            "  export GEE_PROJECT=my-project-123\n"
            "then re-run."
        )

    print(f"Initialising Earth Engine (project={project})...")
    ee.Initialize(project=project)

    print(
        f"Building Sentinel-2 composite  "
        f"{DATE_START} → {DATE_END}, cloud < {MAX_CLOUD_PCT}%"
    )
    image = build_composite()

    print("Downloading preview PNG...")
    save_preview(image)

    print(
        "\nDone. Open the PNG and confirm Karrada is centred.\n"
        f"Path: {OUTPUT_PATH.resolve()}"
    )


if __name__ == "__main__":
    main()
