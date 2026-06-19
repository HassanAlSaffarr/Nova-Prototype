"""Bake display metadata into the v2 high-res detection GeoJSONs.

The v2 detector (nova/highres.py) emits site centroids with {lat, lon, n_cells,
area_m2, mean_delta}. To render them the same way the frontend renders every
other signal, each site needs a stable id and a few display fields. This script
adds them in place, deterministically, so the API can serve the files as-is.

  id          nova-hr-<sha1(lat,lon|after)>  (mirrors v1's nova- scheme)
  method      "highres"                      (lets the UI/panel branch on method)
  detected_at <after> as ISO                 (the "after" capture date)
  before/after dates                         (copied from the FeatureCollection)
  confidence  clamp(mean_delta / 30, .5, .99) — a transparent monotonic proxy:
              a larger structural-density jump ⇒ higher confidence. This is NOT a
              probability; it just orders sites by how strongly structure appeared.
"""

import hashlib
import json
import sys

FILES = [
    "agent/data/detections_karrada_v2.geojson",
    "agent/data/detections_bismayah_v2.geojson",
]


def site_id(lat: float, lon: float, after: str) -> str:
    basis = f"{lat:.6f},{lon:.6f}|{after}"
    return "nova-hr-" + hashlib.sha1(basis.encode()).hexdigest()[:16]


def bake(path: str) -> str:
    d = json.load(open(path))
    fc = d.get("properties", {})
    before, after = fc.get("before", ""), fc.get("after", "")
    detected_at = f"{after}T00:00:00+00:00" if after else ""

    for f in d["features"]:
        p = f["properties"]
        conf = max(0.5, min(0.99, round(p.get("mean_delta", 0) / 30.0, 2)))
        p.update(
            {
                "id": site_id(p["lat"], p["lon"], after),
                "method": "highres",
                "detector": fc.get("detector", "highres-structural-change"),
                "before": before,
                "after": after,
                "detected_at": detected_at,
                "confidence": conf,
                "related_ids": p.get("related_ids", []),
            }
        )
    json.dump(d, open(path, "w"), indent=2, ensure_ascii=False)
    return f"{path}: {len(d['features'])} sites baked (after={after})"


def main() -> None:
    lines = [bake(p) for p in FILES]
    with open("scripts/bake_v2_ids.log", "w") as log:
        log.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
    sys.exit(0)
