"""
Persistent, idempotent store of Nova's detected change sites.

Detections are not events. An event ("Nova scanned Karrada at 09:00") is a moment
and is append-only. A *detection* is a place that persists across scans: when
Nova sees the same site again it should be **updated, not re-appended**. This
store keys sites by their stable id (nova-hr-…), so re-running a scan over an AOI
*converges* instead of duplicating — exactly the property the autonomous loop
(nova/loop.py) needs to run unattended without piling up duplicates.

It is backed by a single GeoJSON (detections_live.geojson) the API can serve
directly (GET /detections?set=live).

Each site also carries a small lifecycle, which answers the open product question
"until when is something *a change*?":
    first_seen   when this loop first detected the site
    last_seen    the most recent cycle that still saw it
    times_seen   how many cycles have confirmed it
    status       "active" while Nova keeps seeing it; completion is later
                 confirmed by the other agents (permits/news), not by imagery.
"""

import json
from datetime import datetime
from pathlib import Path

from nova.config import DATA_DIR

LIVE_PATH = DATA_DIR / "detections_live.geojson"


class DetectionStore:
    """Idempotent GeoJSON-backed store of change sites, keyed by feature id."""

    def __init__(self, path: Path = LIVE_PATH):
        self.path = Path(path)

    # -- io ----------------------------------------------------------------

    def _load(self) -> dict[str, dict]:
        """Return {id: feature}. Empty if the store doesn't exist yet."""
        if not self.path.exists():
            return {}
        fc = json.loads(self.path.read_text())
        return {f["properties"]["id"]: f for f in fc.get("features", [])}

    def _save(self, by_id: dict[str, dict], *, meta: dict | None = None) -> None:
        fc = {
            "type": "FeatureCollection",
            "properties": {"detector": "highres-structural-change",
                           "store": "live", **(meta or {})},
            # newest-confirmed first, then by size — a stable, useful order
            "features": sorted(
                by_id.values(),
                key=lambda f: (
                    f["properties"].get("last_seen", ""),
                    f["properties"].get("area_m2", 0),
                ),
                reverse=True,
            ),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(fc, indent=2, ensure_ascii=False))

    # -- upsert ------------------------------------------------------------

    def upsert(self, features: list[dict], *, now: datetime, aoi: str) -> dict:
        """
        Merge a fresh scan's features into the store, idempotently.

        New ids are added (first_seen = now, times_seen = 1). Existing ids are
        updated in place (geometry/metrics refreshed, last_seen = now, times_seen
        incremented, first_seen preserved). Returns a summary the loop logs.
        """
        by_id = self._load()
        iso = now.isoformat()
        new_ids: list[str] = []
        updated_ids: list[str] = []

        for f in features:
            fid = f["properties"]["id"]
            props = dict(f["properties"])
            if fid in by_id:
                prev = by_id[fid]["properties"]
                props["first_seen"] = prev.get("first_seen", iso)
                props["times_seen"] = int(prev.get("times_seen", 1)) + 1
                props["status"] = prev.get("status", "active")
                updated_ids.append(fid)
            else:
                props["first_seen"] = iso
                props["times_seen"] = 1
                props["status"] = "active"
                new_ids.append(fid)
            props["last_seen"] = iso
            props.setdefault("aoi", aoi)
            by_id[fid] = {**f, "properties": props}

        self._save(by_id, meta={"updated_at": iso, "aoi": aoi})
        return {
            "new": len(new_ids),
            "updated": len(updated_ids),
            "total": len(by_id),
            "new_ids": new_ids,
        }

    # -- read --------------------------------------------------------------

    def all(self) -> list[dict]:
        return list(self._load().values())

    def to_geojson(self) -> dict:
        return {
            "type": "FeatureCollection",
            "features": self.all(),
        }
