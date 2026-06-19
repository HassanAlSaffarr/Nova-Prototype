"""
Spectral band sample renders — what each Sentinel-2 band and index "sees".

For the 2024 (after) composite over Karrada, export grayscale/viridis PNGs to
data/samples/v1/bands/ so the band math in the methodology is tangible:

    b04_red.png    b08_nir.png    b11_swir.png    (raw bands, grayscale)
    ndvi.png       ndbi.png       mndwi.png       (derived indices, viridis)

Raw bands are grayscale (bright = high reflectance); indices are viridis
(yellow = high). Each is captioned with what it reveals.

Usage:
    GEE_PROJECT=... python -m nova.visualize_bands
"""

import os
import sys

import ee
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio

from nova.change_detection import _add_indices, _merge_zip_to_tif
from nova.config import CRS_UTM, KARRADA_BBOX
from nova.visualize import AFTER, CLOUD, RASTER_DIR, SAMPLES_DIR

BANDS_DIR = SAMPLES_DIR / "bands"
BANDS_TIF = RASTER_DIR / "bands_2024.tif"
EXPORT_BANDS = ["B4", "B8", "B11", "NDVI", "NDBI", "MNDWI"]

# (band, filename, colormap, caption)
SPECS = [
    ("B4", "b04_red.png", "gray",
     "B4 Red (665 nm) — built & bare surfaces bright, healthy vegetation dark"),
    ("B8", "b08_nir.png", "gray",
     "B8 Near-infrared (842 nm) — healthy vegetation glows white"),
    ("B11", "b11_swir.png", "gray",
     "B11 Shortwave-infrared (1610 nm) — built/bare bright, water & vegetation dark"),
    ("NDVI", "ndvi.png", "viridis",
     "NDVI = (NIR−Red)/(NIR+Red) — vegetation high (yellow), built/bare low"),
    ("NDBI", "ndbi.png", "viridis",
     "NDBI = (SWIR−NIR)/(SWIR+NIR) — built-up surfaces high (yellow)"),
    ("MNDWI", "mndwi.png", "viridis",
     "MNDWI = (Green−SWIR)/(Green+SWIR) — open water high (yellow) = the Tigris"),
]


def _download_bands_tif() -> None:
    if BANDS_TIF.exists():
        print(f"  bands raster cached: {BANDS_TIF.name}")
        return
    RASTER_DIR.mkdir(parents=True, exist_ok=True)
    aoi = ee.Geometry.Rectangle(KARRADA_BBOX)
    coll = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(AFTER[0], AFTER[1])
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD))
        .map(_add_indices)
    )
    img = coll.select(EXPORT_BANDS).median()
    print(f"  requesting bands {AFTER[0]}->{AFTER[1]} ({coll.size().getInfo()} scenes)...")
    url = img.getDownloadURL({
        "scale": 10, "crs": CRS_UTM, "region": aoi,
        "format": "GEO_TIFF", "bands": EXPORT_BANDS,
    })
    import httpx
    r = httpx.get(url, timeout=300, follow_redirects=True)
    r.raise_for_status()
    if r.content[:2] == b"PK":
        _merge_zip_to_tif(r.content, EXPORT_BANDS, BANDS_TIF)
    else:
        BANDS_TIF.write_bytes(r.content)
    print(f"  saved {BANDS_TIF.name} ({BANDS_TIF.stat().st_size/1e3:.0f} KB)")


def _render(arr: np.ndarray, out, cmap: str, caption: str) -> None:
    finite = np.isfinite(arr)
    vals = arr[finite]
    vmin, vmax = np.percentile(vals, 1), np.percentile(vals, 99)
    display = np.where(finite, arr, np.nan)

    fig, ax = plt.subplots(figsize=(6.2, 6.4))
    fig.patch.set_facecolor("white")
    im = ax.imshow(display, cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_title(caption, fontsize=9, wrap=True)
    ax.axis("off")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out.name}")


def main() -> None:
    project = os.environ.get("GEE_PROJECT")
    if not project:
        sys.exit("GEE_PROJECT is not set.\n  export GEE_PROJECT=your-project-id")

    print(f"Initialising Earth Engine (project={project})...")
    ee.Initialize(project=project)
    BANDS_DIR.mkdir(parents=True, exist_ok=True)

    print("\nDownloading 2024 band composite...")
    _download_bands_tif()

    print("\nRendering band/index samples...")
    with rasterio.open(BANDS_TIF) as src:
        band_index = {name: i + 1 for i, name in enumerate(EXPORT_BANDS)}
        for band, fname, cmap, caption in SPECS:
            arr = src.read(band_index[band]).astype(np.float32)
            if band in ("B4", "B8", "B11"):
                arr[arr == 0] = np.nan  # treat exact-zero reflectance as nodata
            _render(arr, BANDS_DIR / fname, cmap, caption)

    print(f"\nDone. 6 band samples in {BANDS_DIR.resolve()}")


if __name__ == "__main__":
    main()
