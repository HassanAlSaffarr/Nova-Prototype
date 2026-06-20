"""Clean / categorise the v2 detection sets for the demo.

Karrada (built-out): the structure-density signal responds to *any* texture
increase, so the raw scan mixes two genuinely different things:
  - "construction"     — a change sitting in the built fabric (a building
                         footprint within 70 m). New / rebuilt structures.
  - "land_emergence"   — a change with no nearby buildings: a river sandbar or
                         bank exposed as the water dropped. NOT construction, but
                         not noise either — newly usable riverfront land can be
                         commercially meaningful. We keep and *tag* these rather
                         than delete them, so the call on their usefulness is the
                         analyst's, not the filter's.

Bismayah (new city): keep the >= 5,000 m2 "project" floor so the demo shows the
large, real bare->built sites rather than thousands of small noisy cells.

Writes both files back in place (ids/metadata preserved). Idempotent.
"""

import json
import sys

sys.path.insert(0, "agent")

from nova.highres import tag_by_built_fabric  # noqa: E402

KARRADA = "agent/data/detections_karrada_v2.geojson"
BISMAYAH = "agent/data/detections_bismayah_v2.geojson"
FOOTPRINTS = "agent/data/footprints/karrada.min.geojson"
FLOOR_M2 = 5000


def clean_karrada() -> str:
    fc = json.load(open(KARRADA))
    fp = json.load(open(FOOTPRINTS))
    fc["features"] = tag_by_built_fabric(fc["features"], fp, max_m=70.0)
    cats: dict[str, int] = {}
    for f in fc["features"]:
        c = f["properties"]["category"]
        cats[c] = cats.get(c, 0) + 1
    fc["properties"]["categorised"] = "construction vs land_emergence (<=70m of a building)"
    json.dump(fc, open(KARRADA, "w"), indent=2, ensure_ascii=False)
    return f"karrada: {len(fc['features'])} tagged {cats}"


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
