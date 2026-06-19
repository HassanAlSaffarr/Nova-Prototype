"""Smoke-test the autonomous loop in demo mode against temp stores."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, "agent")

from nova.detection_store import DetectionStore  # noqa: E402
from nova.events import EventStore  # noqa: E402
from nova.loop import run_cycle  # noqa: E402

tmp = Path("scripts/_tmp_loop")
tmp.mkdir(exist_ok=True)
store = DetectionStore(path=tmp / "detections_live.geojson")
events = EventStore(db_path=tmp / "events.db")
events.init_db()

t0 = datetime(2026, 6, 20, 8, 0, tzinfo=timezone.utc)
r1 = run_cycle("karrada", live=False, store=store, events=events, now=t0)
r2 = run_cycle("karrada", live=False, store=store, events=events,
               now=t0 + timedelta(hours=6))

out = []
out.append(f"cycle1: triggered={r1['triggered']} new={r1['new']} "
           f"updated={r1['updated']} total={r1['total']}")
out.append(f"cycle2: triggered={r2['triggered']} new={r2['new']} "
           f"updated={r2['updated']} total={r2['total']}")

feats = store.all()
out.append(f"store features={len(feats)}")
p = feats[0]["properties"]
out.append("sample lifecycle: " + ", ".join(
    f"{k}={p.get(k)}" for k in
    ("id", "times_seen", "first_seen", "last_seen", "status", "aoi")
))
out.append(f"events logged={events.count()} latest='{events.latest().message}'")

idempotent = (r1["new"] == r2["updated"] and r2["new"] == 0
              and r1["total"] == r2["total"])
out.append(f"IDEMPOTENT={idempotent}")

Path("scripts/test_loop.log").write_text("\n".join(out) + "\n")
sys.exit(0 if idempotent else 1)
