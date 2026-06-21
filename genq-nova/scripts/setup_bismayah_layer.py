"""Slim Bismayah footprints for the web, and tag Bismayah detections by whether
they sit in the built fabric (construction) or in bare desert (open_land)."""

import json
import os
import sys

sys.path.insert(0, "agent")

from nova.highres import tag_by_built_fabric  # noqa: E402

RAW = "agent/data/footprints/bismayah.geojson"
MIN = "agent/data/footprints/bismayah.min.geojson"
DET = "agent/data/detections_bismayah_v2.geojson"


def round_ring(ring):
    return [[round(x, 6), round(y, 6)] for x, y in ring]


def slim():
    d = json.load(open(RAW))
    out = []
    for f in d["features"]:
        g = f["geometry"]
        if g["type"] == "Polygon":
            coords = [round_ring(r) for r in g["coordinates"]]
        elif g["type"] == "MultiPolygon":
            coords = [[round_ring(r) for r in poly] for poly in g["coordinates"]]
        else:
            continue
        out.append({"type": "Feature", "properties": {},
                    "geometry": {"type": g["type"], "coordinates": coords}})
    json.dump({"type": "FeatureCollection", "name": "bismayah_buildings",
               "features": out}, open(MIN, "w"), separators=(",", ":"))
    return len(out), os.path.getsize(MIN) / 1e6


def tag():
    fc = json.load(open(DET))
    fp = json.load(open(MIN))
    fc["features"] = tag_by_built_fabric(fc["features"], fp, max_m=70.0,
                                         far_category="open_land")
    cats: dict[str, int] = {}
    for f in fc["features"]:
        c = f["properties"]["category"]
        cats[c] = cats.get(c, 0) + 1
    json.dump(fc, open(DET, "w"), indent=2, ensure_ascii=False)
    return cats


def main():
    n, mb = slim()
    cats = tag()
    open("scripts/setup_bismayah.log", "w").write(
        f"slimmed {n} footprints -> {mb:.2f} MB\ndetections tagged: {cats}\n"
    )
    print("DONE")


if __name__ == "__main__":
    main()
