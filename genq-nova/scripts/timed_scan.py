"""Time a full Karrada high-res scan and report coverage + how many changes
exist at different size floors. Writes to a scratch file (not the demo data)."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "agent")

from nova.config import KARRADA_BBOX  # noqa: E402
from nova.highres import scan_aoi  # noqa: E402

BEFORE, AFTER = "2023-12-31", "2026-06-01"
OUT = Path("scripts/_scan_scratch.json")
LOG = Path("scripts/timed_scan.log")

t0 = time.time()
# Low floor (min_cells=10 ≈ 1000 m²) so we see *all* clustered changes, then
# bucket by size below. tile_deg/zoom are the production defaults.
sites = scan_aoi(KARRADA_BBOX, BEFORE, AFTER, min_cells=10, progress=False)
secs = time.time() - t0

w, s, e, n = KARRADA_BBOX
import math
km_w = (e - w) * 111.32 * math.cos(math.radians((s + n) / 2))
km_h = (n - s) * 111.0

buckets = {}
for thr in (1000, 1500, 3000, 5000, 10000):
    buckets[thr] = sum(1 for x in sites if x["area_m2"] >= thr)

lines = [
    f"AOI: Karrada  {km_w:.2f} km x {km_h:.2f} km  = {km_w*km_h:.1f} km^2",
    f"scan wall-time: {secs:.1f} s",
    f"clustered change sites found (min 1000 m^2): {len(sites)}",
    "by size floor:",
]
for thr, c in buckets.items():
    lines.append(f"  >= {thr:>6} m^2 : {c}")
OUT.write_text(json.dumps(sites, indent=1))
LOG.write_text("\n".join(lines) + "\n")
print("DONE")
