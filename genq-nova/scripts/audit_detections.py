"""Audit detection quality: for a sample of sites, pull before/after crops and
measure greenness (vegetation) vs structure, so we can quantify how many are
real construction vs grass/shadow noise. Saves montages for eyeballing."""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, "agent")

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from nova.highres import release_for, wayback_mosaic  # noqa: E402

BEFORE, AFTER = "2023-12-31", "2026-06-01"
HALF_M = 130.0
OUT = Path("scripts/_audit")
OUT.mkdir(parents=True, exist_ok=True)


def greenness(img: Image.Image) -> float:
    """Mean Excess-Green (2G-R-B)/255 — high over vegetation, ~0 over built/bare."""
    a = np.asarray(img.convert("RGB"), np.float32)
    exg = (2 * a[:, :, 1] - a[:, :, 0] - a[:, :, 2]) / 255.0
    return float(exg.mean())


def brightness(img: Image.Image) -> float:
    return float(np.asarray(img.convert("L"), np.float32).mean())


def bbox(lat, lon):
    dlat = HALF_M / 111_000.0
    dlon = HALF_M / (111_320.0 * math.cos(math.radians(lat)))
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


def main():
    rel_b, rel_a = release_for(BEFORE), release_for(AFTER)
    rows = []
    for name in ("karrada", "bismayah"):
        feats = json.load(open(f"agent/data/detections_{name}_v2.geojson"))["features"]
        feats = sorted(feats, key=lambda f: -f["properties"]["area_m2"])
        # sample across the rank: every Nth so we see top, middle, bottom
        step = max(1, len(feats) // 8)
        for i in range(0, len(feats), step):
            p = feats[i]["properties"]
            b = bbox(p["lat"], p["lon"])
            try:
                ib = wayback_mosaic(b, rel_b, 18)
                ia = wayback_mosaic(b, rel_a, 18)
            except Exception as e:
                rows.append(f"{name} rank{i}: FETCH FAIL {e}")
                continue
            gb, ga = greenness(ib), greenness(ia)
            bri = brightness(ia)
            rows.append(
                f"{name} rank{i:>3} area={p['area_m2']:>6} Δ{p['mean_delta']:>5} "
                f"cat={p.get('category','?'):>13} | green_before={gb:+.3f} "
                f"green_after={ga:+.3f} Δgreen={ga-gb:+.3f} bright_after={bri:.0f}"
            )
            # montage
            pa = ia.convert("RGB").resize((300, 300))
            pb = ib.convert("RGB").resize((300, 300))
            m = Image.new("RGB", (606, 320), (10, 14, 26))
            m.paste(pb, (0, 20)); m.paste(pa, (306, 20))
            d = ImageDraw.Draw(m)
            d.text((4, 4), f"{name} r{i} a={p['area_m2']} green_after={ga:+.2f}",
                   fill=(0, 255, 157))
            m.save(OUT / f"{name}_r{i:03d}.png")
    Path("scripts/_audit/audit.log").write_text("\n".join(rows) + "\n")
    print("DONE")


if __name__ == "__main__":
    main()
