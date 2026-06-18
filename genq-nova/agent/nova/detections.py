"""
Unified detection pipeline: combines raster change detection with Microsoft
Building Footprints to produce structured Detection events.

Confidence heuristic (documented here so it can be tuned):

    confidence = 0.40 * ndbi_score
               + 0.30 * area_score
               + 0.20 * footprint_score
               + 0.10 * ndvi_score

  ndbi_score       = min(ΔNDBI / 0.30, 1.0)          — strength of built-surface signal
  area_score       = min(area_m2 / 500.0, 1.0)        — larger polygon = more reliable
  footprint_score  = 1.0 if polygon overlaps footprint else 0.0
  ndvi_score       = min(|ΔNDVI| / 0.20, 1.0)         — corroborating vegetation loss

Detection type assignment:
  "confirmed_change" — change polygon overlaps a Microsoft building footprint, so
                       the change is corroborated by independent building data.
                       Nova does NOT claim a brand-new vertical building — only
                       that a building exists at this changed site.
  "candidate_change" — no footprint overlap; bare-ground change that may or may
                       not be construction (graded land, road, cleared lot, etc.)

Note: MS Global Building Footprints is a single static snapshot with no temporal
dimension, so footprint overlap cannot prove a structure is *new* — only that a
building exists here now. The temporal signal lives entirely in the raster diff.
We therefore only distinguish "footprint present" (confirmed_change) vs "no
footprint" (candidate_change). Distinguishing genuinely new vertical buildings
would need baseline (before-date) footprints — deferred for v2.
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

import geopandas as gpd
from pydantic import BaseModel

from nova.change_detection import detect_changes
from nova.config import CRS_UTM
from nova.footprints import load_karrada_footprints


class Detection(BaseModel):
    id: str
    lat: float
    lon: float
    geometry: dict                          # GeoJSON geometry (WGS84)
    detection_type: Literal["confirmed_change", "candidate_change"]
    confidence: float                       # 0.0 – 1.0
    detected_at: datetime
    source_dates: dict                      # {"before": [start, end], "after": [start, end]}
    area_m2: float
    metadata: dict                          # delta_ndvi, delta_ndbi, delta_brightness


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


def _confidence(
    delta_ndbi: float,
    delta_ndvi: float,
    area_m2: float,
    overlaps_footprint: bool,
) -> float:
    ndbi_score = min(max(delta_ndbi, 0.0) / 0.30, 1.0)
    area_score = min(area_m2 / 500.0, 1.0)
    footprint_score = 1.0 if overlaps_footprint else 0.0
    ndvi_score = min(abs(min(delta_ndvi, 0.0)) / 0.20, 1.0)
    raw = (
        0.40 * ndbi_score
        + 0.30 * area_score
        + 0.20 * footprint_score
        + 0.10 * ndvi_score
    )
    return round(min(max(raw, 0.0), 1.0), 4)


# ---------------------------------------------------------------------------
# Detection type
# ---------------------------------------------------------------------------


def _assign_type(
    overlaps_footprint: bool,
) -> Literal["confirmed_change", "candidate_change"]:
    """A change polygon overlapping a building footprint is a confirmed change
    (corroborated by Microsoft building data); otherwise it's a candidate
    change (bare-ground change that may or may not be construction)."""
    return "confirmed_change" if overlaps_footprint else "candidate_change"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_nova(
    aoi_bounds: list[float],
    date_before: tuple[str, str],
    date_after: tuple[str, str],
    cloud_threshold: int = 20,
) -> list[Detection]:
    """
    Run the full Nova pipeline for one AOI and return structured detections.

    Calls detect_changes() (GEE raster diff) then spatially joins against the
    pre-downloaded Microsoft Building Footprints to classify each detection.

    Assumes ee.Initialize() has already been called.
    """
    print("\n[1/3] Raster change detection via GEE...")
    changes_wgs = detect_changes(
        aoi_bounds,
        date_before,
        date_after,
        cloud_threshold=cloud_threshold,
    )

    if changes_wgs.empty:
        print("No change polygons found — returning empty detections list.")
        return []

    print("\n[2/3] Loading building footprints...")
    footprints_wgs = load_karrada_footprints()
    print(f"  {len(footprints_wgs):,} footprints loaded")

    # Project both to UTM for accurate area & intersection.
    # Reset index so sjoin results align with iterrows indices below.
    changes_utm = changes_wgs.to_crs(CRS_UTM).reset_index(drop=True)
    changes_wgs = changes_wgs.reset_index(drop=True)
    footprints_utm = footprints_wgs.to_crs(CRS_UTM).reset_index(drop=True)

    # Spatial join: find which change polygons overlap at least one footprint.
    # Left join → change polygons with no footprint get NaN in index_right.
    joined = gpd.sjoin(
        changes_utm,
        footprints_utm[["geometry"]],
        how="left",
        predicate="intersects",
    )
    # Multiple footprints may overlap one change polygon — keep the first match.
    joined = joined[~joined.index.duplicated(keep="first")]

    # Build: change_idx (int) → footprint geometry in UTM (or None)
    fp_geom_map: dict[int, object] = {}
    for change_idx, fp_idx in joined["index_right"].items():
        if not _is_null(fp_idx):
            fp_geom_map[int(change_idx)] = footprints_utm.geometry.iloc[int(fp_idx)]

    print("\n[3/3] Building Detection objects...")
    detections: list[Detection] = []
    now = datetime.now(tz=timezone.utc)

    for i, row in changes_utm.iterrows():
        overlaps = fp_geom_map.get(i) is not None
        d_type = _assign_type(overlaps)

        conf = _confidence(
            delta_ndbi=row["delta_ndbi"],
            delta_ndvi=row["delta_ndvi"],
            area_m2=row["area_m2"],
            overlaps_footprint=overlaps,
        )

        wgs_row = changes_wgs.loc[i]
        geom_json = wgs_row.geometry.__geo_interface__

        detections.append(
            Detection(
                id=str(uuid.uuid4()),
                lat=float(wgs_row["centroid_lat"]),
                lon=float(wgs_row["centroid_lon"]),
                geometry=geom_json,
                detection_type=d_type,
                confidence=conf,
                detected_at=now,
                source_dates={
                    "before": list(date_before),
                    "after": list(date_after),
                },
                area_m2=float(row["area_m2"]),
                metadata={
                    "delta_ndvi": round(float(row["delta_ndvi"]), 4),
                    "delta_ndbi": round(float(row["delta_ndbi"]), 4),
                    "delta_brightness": round(float(row["delta_brightness"]), 2),
                    "overlaps_footprint": overlaps,
                },
            )
        )

    detections.sort(key=lambda d: d.confidence, reverse=True)
    print(f"  {len(detections)} detections built")
    return detections


def _is_null(v) -> bool:
    """pandas NA / None / NaN check without importing pandas."""
    if v is None:
        return True
    try:
        import math
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False
