"""
Nova building classifier (CNN) — the v2 precision filter.

The v2 texture detector (highres.py) answers "did detailed *structure* appear
here between two dates?" — but edge density alone fires on parking lots, river
sandbars, desert scrub and material piles just as readily as on real buildings.
This module answers the next question: "is the thing that appeared a *building*?"

A small binary CNN classifies a ~32 m ground crop as building / not-building.
Labels are free: Microsoft ML building footprints rasterised over the same 0.5 m
Esri Wayback imagery the detector uses. Crops sitting on footprints are buildings;
crops over open ground far from any footprint are not. The model is tiny (3 conv
blocks), trains on CPU in minutes, and is reusable on any crop — so it can filter
the texture candidates today and (future) sweep a whole AOI for a building census.

Shared by the training script (scripts/train_building_cnn.py) and the re-tagger.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

# torch is imported lazily inside functions so non-ML callers (the API, the
# detector) don't pay the import cost or hard-fail if it's absent.

CROP_PX = 64                  # 64 px @ ~0.5 m ≈ 32 m window
MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models"
MODEL_PATH = MODEL_DIR / "building_cnn.pt"
META_PATH = MODEL_DIR / "building_cnn.meta.json"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


def build_model():
    """Small 3-block CNN: 3×64×64 RGB → 1 building logit. ~200k params."""
    import torch.nn as nn

    return nn.Sequential(
        nn.Conv2d(3, 16, 3, padding=1), nn.BatchNorm2d(16), nn.ReLU(), nn.MaxPool2d(2),   # 32
        nn.Conv2d(16, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(), nn.MaxPool2d(2),  # 16
        nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(), nn.MaxPool2d(2),  # 8
        nn.AdaptiveAvgPool2d(1), nn.Flatten(),
        nn.Dropout(0.3), nn.Linear(64, 1),
    )


# ---------------------------------------------------------------------------
# Geo helpers — pixel <-> lon/lat over a bbox-aligned mosaic
# ---------------------------------------------------------------------------


def lonlat_to_px(lon: float, lat: float, bbox, W: int, H: int) -> tuple[int, int]:
    w, s, e, n = bbox
    px = (lon - w) / (e - w) * W
    py = (n - lat) / (n - s) * H
    return int(round(px)), int(round(py))


def crop_at(mosaic: np.ndarray, px: int, py: int, size: int = CROP_PX) -> np.ndarray | None:
    """Center crop `size`×`size` from a HxWx3 mosaic; None if it runs off-edge."""
    h = size // 2
    H, W = mosaic.shape[:2]
    if px - h < 0 or py - h < 0 or px + h > W or py + h > H:
        return None
    return mosaic[py - h:py - h + size, px - h:px - h + size]


def black_fraction(crop: np.ndarray) -> float:
    """Fraction of (near-)black pixels — proxy for missing/unfetched tiles."""
    return float((crop.sum(axis=2) < 12).mean())


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------


def load_model():
    """Load the trained model (eval mode) + its meta. Raises if not trained yet."""
    import torch

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"No trained model at {MODEL_PATH}. Run scripts/train_building_cnn.py first."
        )
    meta = json.loads(META_PATH.read_text())
    model = build_model()
    model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
    model.eval()
    return model, meta


def _normalize(crops: np.ndarray, meta: dict):
    """uint8 (N,H,W,3) -> float tensor (N,3,H,W), standardised by training stats."""
    import torch

    x = crops.astype(np.float32) / 255.0
    x = (x - np.array(meta["mean"], np.float32)) / np.array(meta["std"], np.float32)
    return torch.from_numpy(x).permute(0, 3, 1, 2).contiguous()


def predict_crops(model, meta, crops: np.ndarray) -> np.ndarray:
    """Building probability for a batch of uint8 crops (N,H,W,3)."""
    import torch

    if len(crops) == 0:
        return np.zeros(0, np.float32)
    with torch.no_grad():
        logits = model(_normalize(crops, meta)).squeeze(1)
        return torch.sigmoid(logits).numpy()


def building_prob_at(
    model, meta, mosaic: np.ndarray, bbox, lat: float, lon: float,
    area_m2: float = 0.0, size: int = CROP_PX,
) -> float:
    """
    Building probability at a detection. A site can be larger than one crop, so
    we sample a small grid of windows across roughly the site's footprint and
    take the *max* — "is there a building anywhere in this site?" — which is the
    right question for new-construction confirmation.
    """
    H, W = mosaic.shape[:2]
    px, py = lonlat_to_px(lon, lat, bbox, W, H)
    # site radius in px (~0.5 m/px); clamp so we sample a sensible neighbourhood
    r_m = max(16.0, min(80.0, math.sqrt(max(area_m2, 1.0)) / 2))
    r_px = int(r_m / 0.5)
    offs = [-r_px, 0, r_px]
    crops = []
    for dy in offs:
        for dx in offs:
            c = crop_at(mosaic, px + dx, py + dy, size)
            if c is not None and black_fraction(c) < 0.10:
                crops.append(c)
    if not crops:
        return 0.0
    return float(predict_crops(model, meta, np.stack(crops)).max())
