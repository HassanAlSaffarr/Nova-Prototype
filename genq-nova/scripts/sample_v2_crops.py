"""Generate v2 sample data: before/after high-res crops at detected sites.

The v2 detector says "structure appeared on bare land here". This script makes
that visible: for each site it pulls the ~0.5m Esri Wayback mosaic for the
*before* and *after* dates and stitches them side by side, captioned. These are
the demo-able evidence for the high-res method — the visual analogue of v1's
samples/v1/top10_crops, but showing the actual bare→built transition.

Output: agent/data/samples/v2/<aoi>_<NN>_<shortid>.png

Run (needs the venv: httpx/numpy/PIL):
    python scripts/sample_v2_crops.py
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, "agent")

from PIL import Image, ImageDraw  # noqa: E402

from nova.highres import release_for, wayback_mosaic  # noqa: E402

BEFORE, AFTER = "2023-12-31", "2026-06-01"
HALF_M = 130.0          # half-width of the crop window, metres
PANEL = 420             # px per panel after resize
ZOOM = 18
OUT = Path("agent/data/samples/v2")

# (aoi, source file, how many top-by-area sites to render)
JOBS = [
    ("karrada", "agent/data/detections_karrada_v2.geojson", 6),
    ("bismayah", "agent/data/detections_bismayah_v2.geojson", 5),
]


def bbox_around(lat: float, lon: float, half_m: float) -> list[float]:
    dlat = half_m / 111_000.0
    dlon = half_m / (111_320.0 * math.cos(math.radians(lat)))
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


def panel(img: Image.Image) -> Image.Image:
    return img.convert("RGB").resize((PANEL, PANEL))


def caption(img: Image.Image, text: str) -> None:
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, img.width, 18], fill=(10, 14, 26))
    d.text((4, 4), text, fill=(0, 255, 157))


def montage(p_before: Image.Image, p_after: Image.Image, title: str) -> Image.Image:
    w, h = PANEL * 2 + 6, PANEL + 22
    out = Image.new("RGB", (w, h), (10, 14, 26))
    out.paste(p_before, (0, 22))
    out.paste(p_after, (PANEL + 6, 22))
    d = ImageDraw.Draw(out)
    d.text((4, 6), title, fill=(159, 180, 221))
    caption_b = p_before.copy()
    caption(caption_b, f"BEFORE {BEFORE}")
    caption_a = p_after.copy()
    caption(caption_a, f"AFTER {AFTER}")
    out.paste(caption_b, (0, 22))
    out.paste(caption_a, (PANEL + 6, 22))
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rel_b, rel_a = release_for(BEFORE), release_for(AFTER)
    log: list[str] = [f"releases: before={rel_b} after={rel_a}"]

    for aoi, path, n in JOBS:
        feats = json.load(open(path))["features"]
        feats = sorted(feats, key=lambda f: -f["properties"]["area_m2"])[:n]
        for i, f in enumerate(feats, 1):
            p = f["properties"]
            box = bbox_around(p["lat"], p["lon"], HALF_M)
            try:
                pb = panel(wayback_mosaic(box, rel_b, ZOOM))
                pa = panel(wayback_mosaic(box, rel_a, ZOOM))
            except Exception as exc:  # one flaky site shouldn't kill the run
                log.append(f"  {aoi} {i}: FAILED {exc}")
                continue
            title = (f"{aoi.title()} site {i} — {p['area_m2']:,} m²  "
                     f"Δstructure {p['mean_delta']}  ({p['id']})")
            out = montage(pb, pa, title)
            short = p["id"].replace("nova-hr-", "")[:8]
            dst = OUT / f"{aoi}_{i:02d}_{short}.png"
            out.save(dst)
            log.append(f"  {aoi} {i}: {dst.name}  ({p['area_m2']:,} m²)")

    (OUT / "_manifest.txt").write_text("\n".join(log) + "\n")
    Path("scripts/sample_v2_crops.log").write_text("\n".join(log) + "\n")


if __name__ == "__main__":
    main()
    sys.exit(0)
