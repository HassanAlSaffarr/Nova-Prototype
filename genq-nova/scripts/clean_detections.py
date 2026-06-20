"""Clean the v2 detection sets for the demo.

Karrada (built-out): the raw scan also flags river sandbars / exposed banks /
busy parking lots, because the structure-density signal responds to *any* texture
increase. Filter to detections that sit in the built fabric (a building footprint
within 70 m) — this removes the water/open-ground false positives and leaves only
defensible, building-adjacent changes.

Bismayah (new city): keep the >= 5,000 m2 "project" floor so the demo shows the
large, real bare->built sites rather than thousands of small noisy cells.

Writes both files back in place (ids/metadata preserved). Idempotent.
"""

import json
import sys

sys.path.insert(0, "agent")

from nova.highres import filter_to_built_fabric  # noqa: E402

KARRADA = "agent/data/detections_karrada_v2.geojson"
BISMAYAH = "agent/data/detections_bismayah_v2.geojson"
FOOTPRINTS = "agent/data/footprints/karrada.min.geojson"
FLOOR_M2 = 5000


def clean_karrada() -> str:
    fc = json.load(open(KARRADA))
    fp = json.load(open(FOOTPRINTS))
    before = len(fc["features"])
    fc["features"] = filter_to_built_fabric(fc["features"], fp, max_m=70.0)
    fc["properties"]["precision_filter"] = "built-fabric <=70m of a building footprint"
    json.dump(fc, open(KARRADA, "w"), indent=2, ensure_ascii=False)
    return f"karrada: {before} -> {len(fc['features'])} (water/open FPs removed)"


def clean_bismayah() -> str:
    fc = json.load(open(BISMAYAH))
    before = len(fc["features"])
    fc["features"] = [f for f in fc["features"]
                      if f["properties"]["area_m2"] >= FLOOR_M2]
    fc["features"].sort(key=lambda f: -f["properties"]["area_m2"])
    fc["properties"]["floor_m2"] = FLOOR_M2
    json.dump(fc, open(BISMAYAH, "w"), indent=2, ensure_ascii=False)
    return f"bismayah: {before} -> {len(fc['features'])} (>= {FLOOR_M2} m2 floor)"


def main() -> None:
    lines = [clean_karrada(), clean_bismayah()]
    open("scripts/clean_detections.log", "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
    sys.exit(0)
