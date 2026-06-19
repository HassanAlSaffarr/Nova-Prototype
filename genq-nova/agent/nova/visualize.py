"""
Visual sample artifacts for review.

Produces, for the canonical Karrada change-detection run (summer 2022 vs summer
2024):

    data/samples/composite_2022.png       true-colour RGB, before composite
    data/samples/composite_2024.png       true-colour RGB, after composite
    data/samples/diff_visualisation.png   ΔNDBI (red) / ΔNDVI-gain (blue) heatmap
    data/samples/detections_overlay.png   after composite + 50 yellow polygons
    data/samples/top10_crops/             top-10 detection sites, 3-panel montages:
                                          [S2 before | S2 after | Esri hi-res]

Sentinel-2 is what Nova detects on (10 m, what the band math sees). Esri World
Imagery is a crisp visual confirmation backdrop only — it has no SWIR/NIR bands
and no defined acquisition dates, so it cannot drive change detection itself.

Usage:
    GEE_PROJECT=... python -m nova.visualize
"""

import io
import json
import math
import os
import sys
from pathlib import Path

import ee
import httpx
import numpy as np
import rasterio
from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer

from nova.change_detection import _merge_zip_to_tif
from nova.config import CRS_UTM, DATA_DIR, KARRADA_BBOX
from nova.esri import esri_crop

BEFORE = ("2022-06-01", "2022-09-01")
AFTER = ("2024-06-01", "2024-09-01")
CLOUD = 20
RGB_MAX = 3000.0  # S2 SR reflectance value that maps to white

SAMPLES_DIR = DATA_DIR / "samples"
CROPS_DIR = SAMPLES_DIR / "top10_crops"
RASTER_DIR = DATA_DIR / "rasters"
DETECTIONS = DATA_DIR / "detections_karrada.geojson"
DIFF_TIF = RASTER_DIR / "diff_20220601_20220901_vs_20240601_20240901_c20_w.tif"

CROP_HALF_M = 160.0   # 320 m ground window per crop


# ---------------------------------------------------------------------------
# GEE RGB composites (cached as UTM GeoTIFF)
# ---------------------------------------------------------------------------


def _rgb_tif(start: str, end: str) -> Path:
    """Download a true-colour (B4,B3,B2) median composite as a UTM GeoTIFF."""
    stem = f"rgb_{start}_{end}_c{CLOUD}".replace("-", "")
    out = RASTER_DIR / f"{stem}.tif"
    if out.exists():
        print(f"  rgb cached: {out.name}")
        return out

    RASTER_DIR.mkdir(parents=True, exist_ok=True)
    aoi = ee.Geometry.Rectangle(KARRADA_BBOX)
    coll = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD))
    )
    img = coll.select(["B4", "B3", "B2"]).median()
    print(f"  requesting RGB {start}->{end} ({coll.size().getInfo()} scenes)...")
    url = img.getDownloadURL({
        "scale": 10, "crs": CRS_UTM, "region": aoi,
        "format": "GEO_TIFF", "bands": ["B4", "B3", "B2"],
    })
    r = httpx.get(url, timeout=300, follow_redirects=True)
    r.raise_for_status()
    if r.content[:2] == b"PK":
        _merge_zip_to_tif(r.content, ["B4", "B3", "B2"], out)
    else:
        out.write_bytes(r.content)
    print(f"  saved {out.name} ({out.stat().st_size/1e3:.0f} KB)")
    return out


def _read_rgb(tif: Path) -> tuple[np.ndarray, rasterio.Affine]:
    """Read a 3-band RGB GeoTIFF → (HxWx3 uint8, transform)."""
    with rasterio.open(tif) as src:
        bands = [src.read(i).astype(np.float32) for i in (1, 2, 3)]
        transform = src.transform
    rgb = np.stack(bands, axis=-1)
    rgb = np.clip(rgb / RGB_MAX, 0, 1) * 255
    return rgb.astype(np.uint8), transform


# ---------------------------------------------------------------------------
# Top-level PNGs
# ---------------------------------------------------------------------------


def _save_upscaled(rgb: np.ndarray, out: Path, scale: int = 2) -> None:
    img = Image.fromarray(rgb)
    img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    img.save(out)
    print(f"  wrote {out.name}  ({img.width}x{img.height})")


def save_composites() -> tuple[Path, Path]:
    before_tif, after_tif = _rgb_tif(*BEFORE), _rgb_tif(*AFTER)
    rgb_b, _ = _read_rgb(before_tif)
    rgb_a, _ = _read_rgb(after_tif)
    _save_upscaled(rgb_b, SAMPLES_DIR / "composite_2022.png")
    _save_upscaled(rgb_a, SAMPLES_DIR / "composite_2024.png")
    return before_tif, after_tif


def save_diff_heatmap() -> None:
    """Red where ΔNDBI rose (new built surface), blue where vegetation gained."""
    if not DIFF_TIF.exists():
        sys.exit(f"Diff raster missing: {DIFF_TIF}. Run: python -m nova.run")
    with rasterio.open(DIFF_TIF) as src:
        d_ndvi = src.read(1).astype(np.float32)
        d_ndbi = src.read(2).astype(np.float32)

    h, w = d_ndbi.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    red = np.clip(d_ndbi / 0.30, 0, 1)        # built-up gain
    blue = np.clip(d_ndvi / 0.30, 0, 1)       # vegetation gain (ΔNDVI > 0)
    rgba[..., 0] = (red * 255).astype(np.uint8)
    rgba[..., 2] = (blue * 255).astype(np.uint8)
    rgba[..., 3] = (np.maximum(red, blue) * 255).astype(np.uint8)  # transparent elsewhere

    img = Image.fromarray(rgba, mode="RGBA")
    img = img.resize((w * 2, h * 2), Image.NEAREST)
    out = SAMPLES_DIR / "diff_visualisation.png"
    img.save(out)
    print(f"  wrote {out.name}  (red=built-up gain, blue=vegetation gain)")


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def save_detections_overlay(after_tif: Path) -> None:
    """After composite with the 50 detection polygons drawn in yellow + labels."""
    rgb, transform = _read_rgb(after_tif)
    scale = 2
    img = Image.fromarray(rgb).resize(
        (rgb.shape[1] * scale, rgb.shape[0] * scale), Image.NEAREST
    ).convert("RGB")
    draw = ImageDraw.Draw(img)
    font = _font(11)

    fc = json.loads(DETECTIONS.read_text())
    to_utm = Transformer.from_crs("EPSG:4326", CRS_UTM, always_xy=True)
    inv = ~transform

    def to_px(lon, lat):
        x, y = to_utm.transform(lon, lat)
        col, row = inv * (x, y)
        return col * scale, row * scale

    for feat in fc["features"]:
        geom = feat["geometry"]
        polys = (
            [geom["coordinates"]] if geom["type"] == "Polygon"
            else geom["coordinates"]
        )
        for poly in polys:
            ring = [to_px(lon, lat) for lon, lat in poly[0]]
            draw.line(ring + [ring[0]], fill=(255, 230, 0), width=2)
        conf = feat["properties"]["confidence"]
        cx, cy = to_px(feat["properties"]["lon"], feat["properties"]["lat"])
        draw.text((cx + 3, cy - 6), f"{conf:.2f}", fill=(255, 255, 0), font=font)

    out = SAMPLES_DIR / "detections_overlay.png"
    img.save(out)
    print(f"  wrote {out.name}  ({len(fc['features'])} polygons)")


# ---------------------------------------------------------------------------
# S2 crops (Esri hi-res crops come from nova.esri.esri_crop)
# ---------------------------------------------------------------------------


def _s2_crop(rgb: np.ndarray, transform, lat: float, lon: float,
             half_m: float, size: int = 256) -> Image.Image:
    """Window an S2 RGB array around a point and resize to `size`."""
    to_utm = Transformer.from_crs("EPSG:4326", CRS_UTM, always_xy=True)
    x, y = to_utm.transform(lon, lat)
    inv = ~transform
    col, row = inv * (x, y)
    dpx = half_m / 10.0  # 10 m pixels
    c0, c1 = int(col - dpx), int(col + dpx)
    r0, r1 = int(row - dpx), int(row + dpx)
    h, w = rgb.shape[:2]
    c0, c1 = max(0, c0), min(w, c1)
    r0, r1 = max(0, r0), min(h, r1)
    sub = rgb[r0:r1, c0:c1]
    if sub.size == 0:
        sub = np.zeros((1, 1, 3), dtype=np.uint8)
    return Image.fromarray(sub).resize((size, size), Image.NEAREST)


def _montage(panels: list[tuple[str, Image.Image]], title: str) -> Image.Image:
    """Lay out labelled 256px panels side by side under a title bar."""
    size = 256
    head = 26
    cap = 20
    w = size * len(panels)
    out = Image.new("RGB", (w, head + size + cap), (18, 18, 22))
    draw = ImageDraw.Draw(out)
    draw.text((8, 6), title, fill=(255, 255, 255), font=_font(14))
    for i, (label, im) in enumerate(panels):
        out.paste(im, (i * size, head))
        draw.text((i * size + 6, head + size + 3), label,
                  fill=(200, 200, 200), font=_font(12))
    return out


def save_top10_crops(before_tif: Path, after_tif: Path) -> int:
    CROPS_DIR.mkdir(parents=True, exist_ok=True)
    rgb_b, tb = _read_rgb(before_tif)
    rgb_a, ta = _read_rgb(after_tif)

    fc = json.loads(DETECTIONS.read_text())
    top = sorted(fc["features"], key=lambda f: -f["properties"]["confidence"])[:10]

    for i, feat in enumerate(top, 1):
        p = feat["properties"]
        lat, lon, conf = p["lat"], p["lon"], p["confidence"]
        print(f"    det {i:02d} conf={conf:.2f} ({lat:.5f},{lon:.5f})")
        s2_before = _s2_crop(rgb_b, tb, lat, lon, CROP_HALF_M)
        s2_after = _s2_crop(rgb_a, ta, lat, lon, CROP_HALF_M)
        panels = [
            ("S2 BEFORE 2022", s2_before),
            ("S2 AFTER 2024", s2_after),
        ]
        hires = esri_crop(lat, lon, CROP_HALF_M)
        if hires is not None:
            panels.append(("ESRI HI-RES (now)", hires))

        title = f"det_{i:02d}  conf {conf:.2f}  {p['detection_type']}  {p['area_m2']:.0f} m²"
        montage = _montage(panels, title)
        out = CROPS_DIR / f"det_{i:02d}_conf_{conf:.2f}.png"
        montage.save(out)
    return len(top)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    project = os.environ.get("GEE_PROJECT")
    if not project:
        sys.exit("GEE_PROJECT is not set.\n  export GEE_PROJECT=your-project-id")
    if not DETECTIONS.exists():
        sys.exit(f"Detections missing: {DETECTIONS}. Run: python -m nova.run")

    print(f"Initialising Earth Engine (project={project})...")
    ee.Initialize(project=project)
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/4] RGB composites...")
    before_tif, after_tif = save_composites()
    print("\n[2/4] Diff heatmap...")
    save_diff_heatmap()
    print("\n[3/4] Detections overlay...")
    save_detections_overlay(after_tif)
    print("\n[4/4] Top-10 crops (S2 + Esri hi-res)...")
    n = save_top10_crops(before_tif, after_tif)

    print(f"\nDone. {n} crop montages + 4 overview PNGs in {SAMPLES_DIR.resolve()}")


if __name__ == "__main__":
    main()
