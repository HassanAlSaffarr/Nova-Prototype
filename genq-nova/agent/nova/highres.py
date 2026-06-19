"""
Nova v2 detector — high-resolution structural-change detection.

Replaces v1's 10m optical indices (NDVI/NDBI), which were empirically falsified:
at 10m a building is 1-4 noisy pixels and bare soil mimics built-up (NDBI), so
index- and SAR-backscatter-thresholding could not tell construction from a
saturated district (SAR fired equally on a 100k-unit megaproject and built-out
Karrada). The fix is resolution, not a better index.

This detector works on ~0.5m Esri World Imagery, pulled FREE for two dates from
the World Imagery Wayback archive (≈190 dated versions back to 2014). New
construction shows up as *structure appearing where there was smooth bare land*:
the local image-gradient ("structure density") rises sharply from a low baseline.

Validated on ground truth: flags 31% of Bismayah New City (known active
construction) vs 5% of saturated Karrada — a ~6x discrimination, where 10m
optical and SAR managed ~1x.

This is the high-precision Tier-2 of the planned pipeline (Sentinel = cheap
trigger -> high-res confirm -> internet verify). A DL building-segmentation model
is the natural upgrade from this classical structure signal.
"""

import io
import json
import math
from collections import deque
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

WAYBACK_CONFIG = (
    "https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json"
)
WAYBACK_TILE = (
    "https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/"
    "WMTS/1.0.0/default028mm/MapServer/tile/{release}/{z}/{y}/{x}"
)


# ---------------------------------------------------------------------------
# Wayback archive
# ---------------------------------------------------------------------------


def wayback_releases() -> list[tuple[str, str]]:
    """Return [(release_id, 'YYYY-MM-DD'), ...] sorted oldest→newest."""
    r = httpx.get(WAYBACK_CONFIG, timeout=40, follow_redirects=True)
    r.raise_for_status()
    out = []
    for rel, v in r.json().items():
        title = v.get("itemTitle", "") if isinstance(v, dict) else ""
        i = title.find("Wayback ")
        date = title[i + 8 : i + 18] if i >= 0 else ""
        if date:
            out.append((rel, date))
    return sorted(out, key=lambda t: t[1])


def release_for(date: str) -> str:
    """Release id of the latest Wayback version on or before `date` (YYYY-MM-DD)."""
    rels = [r for r in wayback_releases() if r[1] <= date]
    if not rels:
        raise ValueError(f"No Wayback release on or before {date}")
    return rels[-1][0]


def _deg2tile(lat: float, lon: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (
        1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat)))
        / math.pi
    ) / 2 * n
    return x, y


def wayback_mosaic(bbox: list[float], release: str, zoom: int = 18) -> Image.Image:
    """Stitch a Wayback high-res RGB mosaic for bbox [w,s,e,n] at a given release."""
    w, s, e, n = bbox
    x0f, y0f = _deg2tile(n, w, zoom)
    x1f, y1f = _deg2tile(s, e, zoom)
    x0, y0, x1, y1 = int(x0f), int(y0f), int(x1f), int(y1f)
    mos = Image.new("RGB", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256))
    with httpx.Client(timeout=30, follow_redirects=True) as c:
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                resp = c.get(WAYBACK_TILE.format(release=release, z=zoom, y=ty, x=tx))
                if resp.status_code == 200:
                    tile = Image.open(io.BytesIO(resp.content)).convert("RGB")
                    mos.paste(tile, ((tx - x0) * 256, (ty - y0) * 256))
    left, top = int((x0f - x0) * 256), int((y0f - y0) * 256)
    right, bot = int((x1f - x0) * 256), int((y1f - y0) * 256)
    return mos.crop((left, top, right, bot))


# ---------------------------------------------------------------------------
# Structural-change detection
# ---------------------------------------------------------------------------


def structure_density(gray: np.ndarray, win: int) -> np.ndarray:
    """Mean image-gradient magnitude aggregated to win×win cells.
    High over edged/built structure, low over smooth bare land/desert."""
    gx = np.zeros_like(gray)
    gy = np.zeros_like(gray)
    gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
    gy[1:-1, :] = gray[2:, :] - gray[:-2, :]
    mag = np.sqrt(gx * gx + gy * gy)
    h2 = mag.shape[0] // win * win
    w2 = mag.shape[1] // win * win
    return mag[:h2, :w2].reshape(h2 // win, win, w2 // win, win).mean((1, 3))


def detect_new_construction(
    bbox: list[float],
    date_before: str,
    date_after: str,
    zoom: int = 18,
    cell_px: int = 20,           # 20 px @ ~0.5m ≈ 10 m cells
    change_thresh: float = 8.0,  # structure-density rise that counts as "appeared"
    bare_before: float = 12.0,   # was relatively smooth/bare beforehand
) -> dict:
    """
    Detect new construction between two dates from Wayback high-res imagery.

    Returns a dict with the flagged-cell mask, the per-cell structure grids, and
    a list of detection cells [{lat, lon, struct_before, struct_after, delta}].
    """
    rel_b, rel_a = release_for(date_before), release_for(date_after)
    gb = np.asarray(wayback_mosaic(bbox, rel_b, zoom).convert("L"), np.float32)
    ga = np.asarray(wayback_mosaic(bbox, rel_a, zoom).convert("L"), np.float32)
    h, w = min(gb.shape[0], ga.shape[0]), min(gb.shape[1], ga.shape[1])

    sb = structure_density(gb[:h, :w], cell_px)
    sa = structure_density(ga[:h, :w], cell_px)
    H, W = min(sb.shape[0], sa.shape[0]), min(sb.shape[1], sa.shape[1])
    sb, sa = sb[:H, :W], sa[:H, :W]

    new = (sa - sb > change_thresh) & (sb < bare_before)

    west, south, east, north = bbox
    dets = []
    for i, j in zip(*np.where(new)):
        lon = west + (j + 0.5) / W * (east - west)
        lat = north - (i + 0.5) / H * (north - south)
        dets.append({
            "lat": round(lat, 6), "lon": round(lon, 6),
            "struct_before": round(float(sb[i, j]), 1),
            "struct_after": round(float(sa[i, j]), 1),
            "delta": round(float(sa[i, j] - sb[i, j]), 1),
        })
    return {
        "release_before": (rel_b, date_before),
        "release_after": (rel_a, date_after),
        "cells": int(H * W),
        "flagged": int(new.sum()),
        "flagged_pct": round(100 * float(new.mean()), 1),
        "detections": dets,
    }


# ---------------------------------------------------------------------------
# Full-AOI scan: tile the AOI, detect per tile, cluster cells into project sites
# ---------------------------------------------------------------------------


def _connected_components(occ: np.ndarray) -> list[list[tuple[int, int]]]:
    """8-connected components of a boolean grid (BFS, no scipy)."""
    seen = np.zeros_like(occ, dtype=bool)
    comps: list[list[tuple[int, int]]] = []
    ny, nx = occ.shape
    for y in range(ny):
        for x in range(nx):
            if occ[y, x] and not seen[y, x]:
                q = deque([(y, x)])
                seen[y, x] = True
                cells = []
                while q:
                    cy, cx = q.popleft()
                    cells.append((cy, cx))
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            ny2, nx2 = cy + dy, cx + dx
                            if 0 <= ny2 < ny and 0 <= nx2 < nx and occ[ny2, nx2] and not seen[ny2, nx2]:
                                seen[ny2, nx2] = True
                                q.append((ny2, nx2))
                comps.append(cells)
    return comps


def scan_aoi(
    bbox: list[float],
    date_before: str,
    date_after: str,
    tile_deg: float = 0.009,   # ~1 km tiles
    zoom: int = 18,
    grid_m: float = 10.0,
    min_cells: int = 3,        # >= ~300 m² of flagged area to count as a site
    progress: bool = True,
) -> list[dict]:
    """
    Scan a whole AOI for new construction: tile it, run the high-res detector on
    each tile, then cluster all flagged cells into discrete project sites.

    Returns sites [{lat, lon, n_cells, area_m2, mean_delta}] sorted by size.
    """
    w, s, e, n = bbox
    cos = math.cos(math.radians((s + n) / 2))
    all_dets: list[dict] = []

    lat = s
    nrows = max(1, math.ceil((n - s) / tile_deg))
    ncols = max(1, math.ceil((e - w) / tile_deg))
    t = 0
    while lat < n:
        lon = w
        while lon < e:
            tb = [lon, lat, min(lon + tile_deg, e), min(lat + tile_deg, n)]
            try:
                res = detect_new_construction(tb, date_before, date_after, zoom=zoom)
                all_dets.extend(res["detections"])
            except Exception as exc:  # one bad tile shouldn't kill the scan
                if progress:
                    print(f"    tile {t} failed: {exc}")
            t += 1
            if progress:
                print(f"    tile {t}/{nrows * ncols}: {len(all_dets)} flagged cells so far")
            lon += tile_deg
        lat += tile_deg

    if not all_dets:
        return []

    # Global occupancy grid → connected components = project sites.
    ny = int((n - s) * 111_000 / grid_m) + 1
    nx = int((e - w) * 111_320 * cos / grid_m) + 1
    occ = np.zeros((ny, nx), dtype=bool)
    cell_delta: dict[tuple[int, int], float] = {}
    for d in all_dets:
        gy = int((n - d["lat"]) * 111_000 / grid_m)
        gx = int((d["lon"] - w) * 111_320 * cos / grid_m)
        if 0 <= gy < ny and 0 <= gx < nx:
            occ[gy, gx] = True
            cell_delta[(gy, gx)] = max(cell_delta.get((gy, gx), 0.0), d["delta"])

    sites: list[dict] = []
    for comp in _connected_components(occ):
        if len(comp) < min_cells:
            continue
        cy = np.mean([c[0] for c in comp])
        cx = np.mean([c[1] for c in comp])
        lat_c = n - (cy + 0.5) * grid_m / 111_000
        lon_c = w + (cx + 0.5) * grid_m / (111_320 * cos)
        deltas = [cell_delta[c] for c in comp]
        sites.append({
            "lat": round(lat_c, 6), "lon": round(lon_c, 6),
            "n_cells": len(comp),
            "area_m2": round(len(comp) * grid_m * grid_m),
            "mean_delta": round(float(np.mean(deltas)), 1),
        })
    sites.sort(key=lambda x: -x["n_cells"])
    return sites


def sites_to_geojson(sites: list[dict], date_before: str, date_after: str) -> dict:
    return {
        "type": "FeatureCollection",
        "properties": {"detector": "highres-structural-change",
                       "before": date_before, "after": date_after},
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
                "properties": s,
            }
            for s in sites
        ],
    }

