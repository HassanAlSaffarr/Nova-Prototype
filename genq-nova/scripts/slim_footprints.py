"""Slim the MS building-footprints GeoJSON for web serving.

The raw Microsoft Global ML footprints carry ~15-decimal coordinates (sub-micron,
meaningless at 0.5 m imagery) and placeholder-only properties (height/confidence
== -1). We round coordinates to 6 dp (~0.1 m) and drop properties, cutting the
payload by more than half so 24k polygons parse fast in the browser.
"""

import json
import os
import sys

SRC = "agent/data/footprints/karrada.geojson"
DST = "agent/data/footprints/karrada.min.geojson"


def round_ring(ring):
    return [[round(x, 6), round(y, 6)] for x, y in ring]


def main() -> None:
    d = json.load(open(SRC))
    feats = d["features"]

    real_h = sum(
        1 for f in feats if f.get("properties", {}).get("height", -1) not in (-1, -1.0)
    )
    real_c = sum(
        1
        for f in feats
        if f.get("properties", {}).get("confidence", -1) not in (-1, -1.0)
    )

    out = []
    for f in feats:
        g = f["geometry"]
        if g["type"] == "Polygon":
            coords = [round_ring(r) for r in g["coordinates"]]
        elif g["type"] == "MultiPolygon":
            coords = [[round_ring(r) for r in poly] for poly in g["coordinates"]]
        else:
            continue
        out.append(
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": g["type"], "coordinates": coords},
            }
        )

    slim = {"type": "FeatureCollection", "name": "karrada_buildings", "features": out}
    json.dump(slim, open(DST, "w"), separators=(",", ":"))

    with open("scripts/slim_footprints.log", "w") as log:
        log.write(f"features={len(feats)} real_height={real_h} real_confidence={real_c}\n")
        log.write(
            f"wrote {DST}: {os.path.getsize(DST)/1e6:.2f} MB "
            f"(was {os.path.getsize(SRC)/1e6:.2f} MB) features={len(out)}\n"
        )


if __name__ == "__main__":
    main()
    sys.exit(0)
