"""
Re-tag v2 detections with the trained building CNN (nova/cnn.py).

The texture detector flags "structure appeared"; the CNN decides whether that
structure is a *building*. Each detection's category is reset to:
    building prob >= THRESH -> "construction"   (green on the map)
    else                    -> the AOI's far category (grey; stays on the map)
We also write `cnn_prob` onto every feature for transparency in the side panel.

Reuses the mosaics cached by train_building_cnn.py, so it makes no network calls.

Usage:  agent/.venv/bin/python scripts/retag_with_cnn.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

from nova import cnn  # noqa: E402
from nova.config import AOI_PRESETS  # noqa: E402

CACHE = ROOT / "agent" / "data" / "cache" / "cnn"
DATA = ROOT / "agent" / "data"
THRESH = 0.5

# AOI -> (detections file, after date, far category for non-buildings)
AOIS = {
    "karrada": ("detections_karrada_v2.geojson", "2026-06-01", "land_emergence"),
    "bismayah": ("detections_bismayah_v2.geojson", "2026-06-01", "open_land"),
}


def main():
    model, meta = cnn.load_model()
    print(f"Loaded model (val_acc {meta.get('val_acc')}), thresh {THRESH}\n")

    for aoi, (det_file, after, far_cat) in AOIS.items():
        bbox = AOI_PRESETS[aoi]
        mosaic = np.load(CACHE / f"{aoi}_mosaic_{after}.npy")
        det_path = DATA / det_file
        d = json.loads(det_path.read_text())

        n_build = 0
        for f in d["features"]:
            p = f["properties"]
            prob = cnn.building_prob_at(
                model, meta, mosaic, bbox,
                lat=p["lat"], lon=p["lon"], area_m2=float(p.get("area_m2", 0)),
            )
            p["cnn_prob"] = round(prob, 3)
            is_building = prob >= THRESH
            p["category"] = "construction" if is_building else far_cat
            n_build += int(is_building)

        det_path.write_text(json.dumps(d, indent=2))
        n = len(d["features"])
        print(f"[{aoi}] {n_build}/{n} construction, {n - n_build} {far_cat}  -> {det_file}")


if __name__ == "__main__":
    main()
