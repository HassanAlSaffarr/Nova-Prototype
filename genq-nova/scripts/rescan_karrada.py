"""Re-scan Karrada at the 3,000 m2 floor and rebuild the demo detection set.

Pipeline (mirrors how the canonical v2 files were made):
  scan_aoi -> sites_to_geojson -> bake ids/metadata -> tag construction vs
  land_emergence -> write detections_karrada_v2.geojson.
"""

import hashlib
import json
import sys

sys.path.insert(0, "agent")

from nova.config import KARRADA_BBOX  # noqa: E402
from nova.highres import scan_aoi, sites_to_geojson, tag_by_built_fabric  # noqa: E402

BEFORE, AFTER = "2023-12-31", "2026-06-01"
MIN_CELLS = 30  # 30 cells x 100 m2 = 3,000 m2 floor
OUT = "agent/data/detections_karrada_v2.geojson"
FOOTPRINTS = "agent/data/footprints/karrada.min.geojson"


def site_id(lat: float, lon: float) -> str:
    return "nova-hr-" + hashlib.sha1(
        f"{lat:.6f},{lon:.6f}|{AFTER}".encode()
    ).hexdigest()[:16]


def main() -> None:
    sites = scan_aoi(KARRADA_BBOX, BEFORE, AFTER, min_cells=MIN_CELLS, progress=False)
    fc = sites_to_geojson(sites, BEFORE, AFTER)
    detected_at = f"{AFTER}T00:00:00+00:00"

    for f in fc["features"]:
        p = f["properties"]
        conf = max(0.5, min(0.99, round(p.get("mean_delta", 0) / 30.0, 2)))
        p.update({
            "id": site_id(p["lat"], p["lon"]),
            "method": "highres",
            "detector": "highres-structural-change",
            "before": BEFORE,
            "after": AFTER,
            "detected_at": detected_at,
            "confidence": conf,
            "related_ids": [],
        })

    fp = json.load(open(FOOTPRINTS))
    fc["features"] = tag_by_built_fabric(fc["features"], fp, max_m=70.0)
    fc["properties"]["floor_m2"] = MIN_CELLS * 100
    fc["properties"]["categorised"] = "construction vs land_emergence (<=70m of a building)"

    json.dump(fc, open(OUT, "w"), indent=2, ensure_ascii=False)

    cats: dict[str, int] = {}
    for f in fc["features"]:
        c = f["properties"]["category"]
        cats[c] = cats.get(c, 0) + 1
    with open("scripts/rescan_karrada.log", "w") as log:
        log.write(f"{len(fc['features'])} sites at >={MIN_CELLS*100} m2 floor; {cats}\n")
    print("DONE")


if __name__ == "__main__":
    main()
