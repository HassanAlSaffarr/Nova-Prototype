"""
Train Nova's building classifier (the v2 precision filter).

Pipeline, fully self-contained and reproducible:
  1. For each AOI, stitch the 0.5 m Esri Wayback mosaic at the detector's "after"
     date and rasterise the Microsoft building footprints into an aligned mask
     (cached to data/cache/cnn so re-runs are instant).
  2. Sample labelled crops for free from that alignment:
       positive = a ~32 m crop sitting on a footprint (a building)
       negative = a ~32 m crop of real imagery with NO footprint (desert, river,
                  vegetation, roads, parking, bare lots)
  3. Train the small CNN (nova/cnn.py) and save weights + normalisation meta.

Usage:  agent/.venv/bin/python scripts/train_building_cnn.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

from nova import cnn  # noqa: E402
from nova.config import AOI_PRESETS  # noqa: E402
from nova.highres import release_for, wayback_mosaic  # noqa: E402

CACHE = ROOT / "agent" / "data" / "cache" / "cnn"
CACHE.mkdir(parents=True, exist_ok=True)

# AOI -> (footprints file, detector "after" date). Two complementary domains:
# dense urban Karrada and desert new-city Bismayah, so the model sees buildings
# and non-buildings from both.
AOIS = {
    "karrada": ("karrada.min.geojson", "2026-06-01"),
    "bismayah": ("bismayah.min.geojson", "2026-06-01"),
}
ZOOM = 18
POS_PER_AOI = 1400
NEG_PER_AOI = 1400
RNG = np.random.default_rng(42)


# ---------------------------------------------------------------------------
# Mosaic + aligned building mask (cached)
# ---------------------------------------------------------------------------


def _footprint_rings(fp_path: Path):
    d = json.loads(fp_path.read_text())
    for f in d["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            yield poly[0]  # outer ring


def build_mosaic_and_mask(aoi: str):
    bbox = AOI_PRESETS[aoi]
    fp_file, after = AOIS[aoi]
    mos_path = CACHE / f"{aoi}_mosaic_{after}.npy"
    mask_path = CACHE / f"{aoi}_mask_{after}.npy"
    if mos_path.exists() and mask_path.exists():
        print(f"  [{aoi}] cache hit")
        return np.load(mos_path), np.load(mask_path), bbox

    print(f"  [{aoi}] stitching Wayback mosaic @ {after} (this is the slow part)...")
    rel = release_for(after)
    img = wayback_mosaic(bbox, rel, zoom=ZOOM, workers=24)
    mosaic = np.asarray(img.convert("RGB"), np.uint8)
    H, W = mosaic.shape[:2]
    print(f"  [{aoi}] mosaic {W}x{H}px; rasterising footprints...")

    mask_img = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(mask_img)
    n = 0
    for ring in _footprint_rings(ROOT / "agent" / "data" / "footprints" / fp_file):
        pix = [cnn.lonlat_to_px(lon, lat, bbox, W, H) for lon, lat in ring]
        if len(pix) >= 3:
            draw.polygon(pix, fill=1)
            n += 1
    mask = np.asarray(mask_img, bool)
    print(f"  [{aoi}] drew {n} footprints; building coverage {100*mask.mean():.1f}%")

    np.save(mos_path, mosaic)
    np.save(mask_path, mask)
    return mosaic, mask, bbox


# ---------------------------------------------------------------------------
# Crop sampling
# ---------------------------------------------------------------------------


def sample_crops(mosaic, mask, *, n_pos, n_neg, size=cnn.CROP_PX):
    H, W = mosaic.shape[:2]
    h = size // 2
    pos, neg = [], []

    # Positives: centers of building pixels. Sample building-pixel coordinates,
    # require the crop to be meaningfully on a building and not on a black edge.
    bys, bxs = np.where(mask)
    idx = RNG.permutation(len(bys))
    for k in idx:
        if len(pos) >= n_pos:
            break
        py, px = int(bys[k]), int(bxs[k])
        c = cnn.crop_at(mosaic, px, py, size)
        if c is None or cnn.black_fraction(c) > 0.05:
            continue
        mcrop = mask[py - h:py - h + size, px - h:px - h + size]
        if mcrop.mean() >= 0.08:  # crop genuinely contains a building
            pos.append(c)

    # Negatives: random points with NO building in the crop, on real imagery.
    tries = 0
    while len(neg) < n_neg and tries < n_neg * 60:
        tries += 1
        px = int(RNG.integers(h, W - h))
        py = int(RNG.integers(h, H - h))
        mcrop = mask[py - h:py - h + size, px - h:px - h + size]
        if mcrop.any():
            continue
        c = cnn.crop_at(mosaic, px, py, size)
        if c is None or cnn.black_fraction(c) > 0.02:
            continue
        neg.append(c)

    return pos, neg


def augment(crops: np.ndarray) -> np.ndarray:
    """4x: original + hflip + vflip + rot90 (buildings are orientation-agnostic)."""
    out = [crops, crops[:, :, ::-1], crops[:, ::-1], np.rot90(crops, 1, (1, 2))]
    return np.concatenate(out)


# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------


def main():
    t0 = time.time()
    print("Building per-AOI mosaics + masks...")
    X_pos, X_neg = [], []
    for aoi in AOIS:
        mosaic, mask, _ = build_mosaic_and_mask(aoi)
        pos, neg = sample_crops(mosaic, mask, n_pos=POS_PER_AOI, n_neg=NEG_PER_AOI)
        print(f"  [{aoi}] sampled {len(pos)} pos / {len(neg)} neg crops")
        X_pos += pos
        X_neg += neg

    Xp = np.stack(X_pos)
    Xn = np.stack(X_neg)
    X = np.concatenate([Xp, Xn]).astype(np.uint8)
    y = np.concatenate([np.ones(len(Xp)), np.zeros(len(Xn))]).astype(np.float32)
    print(f"\nDataset: {len(X)} crops ({len(Xp)} building / {len(Xn)} not)")

    # Split BEFORE augmentation so flips of a train crop never leak into val.
    perm = RNG.permutation(len(X))
    X, y = X[perm], y[perm]
    n_val = int(0.15 * len(X))
    Xv, yv = X[:n_val], y[:n_val]
    Xt, yt = X[n_val:], y[n_val:]
    Xt = augment(Xt)
    yt = np.concatenate([yt] * 4)
    print(f"Train {len(Xt)} (augmented) / Val {len(Xv)}")

    mean = (Xt.astype(np.float32) / 255).reshape(-1, 3).mean(0)
    std = (Xt.astype(np.float32) / 255).reshape(-1, 3).std(0)
    meta = {"crop_px": cnn.CROP_PX, "mean": mean.tolist(), "std": std.tolist(),
            "aois": list(AOIS), "after": "2026-06-01"}

    import torch
    from torch.utils.data import DataLoader, TensorDataset

    torch.manual_seed(0)
    Xt_t = cnn._normalize(Xt, meta)
    Xv_t = cnn._normalize(Xv, meta)
    yt_t = torch.from_numpy(yt)
    yv_t = torch.from_numpy(yv)
    train_dl = DataLoader(TensorDataset(Xt_t, yt_t), batch_size=64, shuffle=True)

    model = cnn.build_model()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    lossf = torch.nn.BCEWithLogitsLoss()

    EPOCHS = 18
    best_acc, best_state = 0.0, None
    for ep in range(1, EPOCHS + 1):
        model.train()
        for xb, yb in train_dl:
            opt.zero_grad()
            loss = lossf(model(xb).squeeze(1), yb)
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            pv = torch.sigmoid(model(Xv_t).squeeze(1)).numpy()
        pred = (pv >= 0.5).astype(np.float32)
        acc = float((pred == yv).mean())
        tp = float(((pred == 1) & (yv == 1)).sum())
        prec = tp / max(1.0, float((pred == 1).sum()))
        rec = tp / max(1.0, float((yv == 1).sum()))
        print(f"  epoch {ep:2d}  val_acc {acc:.3f}  prec {prec:.3f}  rec {rec:.3f}")
        if acc >= best_acc:
            best_acc, best_state = acc, {k: v.clone() for k, v in model.state_dict().items()}

    cnn.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(best_state, cnn.MODEL_PATH)
    meta["val_acc"] = round(best_acc, 4)
    cnn.META_PATH.write_text(json.dumps(meta, indent=2))
    print(f"\nSaved model -> {cnn.MODEL_PATH}  (best val_acc {best_acc:.3f})")
    print(f"Done in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
