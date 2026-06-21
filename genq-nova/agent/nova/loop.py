"""
Nova's autonomous loop — the agentic heartbeat (concern #2).

Nova is not run by a button; it runs itself. Each cycle:

  1. trigger   — a cheap Sentinel pass says "something may have changed here"
                 (live mode counts S1 scenes; demo mode simulates the trigger).
  2. scan      — the high-res structural-change detector finds *where* it changed.
  3. upsert    — sites are merged into the live detection store idempotently, so
                 re-running converges instead of duplicating (DetectionStore).
  4. log       — a run event is appended so the UI's event log ticks on its own.

Two modes:
  demo (default)  replay the committed high-res scan output (detections_<aoi>_v2
                  .geojson) as this cycle's result — no GEE, no network, so the
                  loop is demoable anywhere. Running twice shows idempotency:
                  cycle 1 = N new, cycle 2 = 0 new / N updated.
  live (--live)   actually scan Wayback imagery via nova.highres (needs the GEE
                  env for the trigger, numpy/PIL for the scan).

Run:
  python -m nova.loop --once                  # one demo cycle
  python -m nova.loop --interval 30           # demo cycle every 30s
  python -m nova.loop --live --aoi karrada    # real scan
"""

import argparse
import hashlib
import time
from datetime import datetime, timezone

from nova.config import AOI_PRESETS, DATA_DIR
from nova.detection_store import DetectionStore
from nova.events import Event, EventStore, _new_id

# Default date window for the high-res before/after comparison (live mode).
BEFORE_DATE = "2023-12-31"
AFTER_DATE = "2026-06-01"

# Per-AOI label for sites the CNN judges are NOT buildings (kept, shown grey).
FAR_CATEGORY = {"karrada": "land_emergence", "bismayah": "open_land"}


def _site_id(lat: float, lon: float, after: str) -> str:
    """Stable high-res site id — mirrors scripts/bake_v2_ids.py so demo (baked)
    and live (computed here) sites share the same id space and converge."""
    return "nova-hr-" + hashlib.sha1(
        f"{lat:.6f},{lon:.6f}|{after}".encode()
    ).hexdigest()[:16]


# ---------------------------------------------------------------------------
# One cycle
# ---------------------------------------------------------------------------


def _trigger(aoi: str, live: bool, force: bool = False) -> dict:
    """Cheap coarse trigger. Live mode counts Sentinel-1 scenes over the AOI;
    demo mode simulates a positive trigger so the loop runs end-to-end. `force`
    bypasses the Sentinel check (and its GEE dependency) entirely — used when the
    loop is hosted somewhere without GEE credentials but can still scan Wayback."""
    if not live or force:
        return {"source": "forced" if force else "simulated", "triggered": True}
    from nova.sar import scene_counts  # lazy: avoids ee import in demo mode

    bounds = AOI_PRESETS[aoi]
    before, after = scene_counts(
        bounds, (BEFORE_DATE, "2024-03-01"), ("2026-03-01", AFTER_DATE)
    )
    return {"source": "sentinel-1", "triggered": before > 0 and after > 0,
            "scenes_before": before, "scenes_after": after}


def _scan_sites(aoi: str, live: bool) -> list[dict]:
    """Return this cycle's detected sites as GeoJSON features (with ids)."""
    if not live:
        import json
        path = DATA_DIR / f"detections_{aoi}_v2.geojson"
        if not path.exists():
            raise FileNotFoundError(
                f"No cached scan for '{aoi}' at {path.name}. Run a live scan "
                f"first or pick another AOI."
            )
        return json.loads(path.read_text()).get("features", [])

    from nova.highres import scan_aoi, sites_to_geojson  # lazy import

    sites = scan_aoi(AOI_PRESETS[aoi], BEFORE_DATE, AFTER_DATE, progress=False)
    fc = sites_to_geojson(sites, BEFORE_DATE, AFTER_DATE)
    for f in fc["features"]:
        p = f["properties"]
        p["id"] = _site_id(p["lat"], p["lon"], AFTER_DATE)
        p["method"] = "highres"
    _classify(fc["features"], aoi)
    return fc["features"]


def _classify(features: list[dict], aoi: str) -> None:
    """Run the building CNN over a live scan's sites, setting `category` and
    `cnn_prob` in place. The detector says *where* structure appeared; this says
    *whether it's a building* (green) or other change (grey). No-op (everything
    stays construction) if the model isn't present, so the loop still runs."""
    if not features:
        return
    try:
        from nova import cnn  # lazy: torch only loaded for live+classify
        model, meta = cnn.load_model()
    except Exception as exc:  # no torch / no trained model — degrade gracefully
        print(f"    CNN classify skipped: {exc}")
        return

    far_cat = FAR_CATEGORY.get(aoi, "open_land")
    for f in features:
        p = f["properties"]
        prob = cnn.building_prob_live(
            model, meta, p["lat"], p["lon"], AFTER_DATE, float(p.get("area_m2", 0))
        )
        p["cnn_prob"] = round(prob, 3)
        p["category"] = "construction" if prob >= 0.5 else far_cat


def run_cycle(aoi: str = "karrada", *, live: bool = False, force: bool = False,
              store: DetectionStore | None = None,
              events: EventStore | None = None,
              now: datetime | None = None) -> dict:
    """Run one autonomous cycle: trigger → scan → idempotent upsert → log."""
    store = store or DetectionStore()
    events = events or EventStore()
    events.init_db()
    now = now or datetime.now(tz=timezone.utc)

    trig = _trigger(aoi, live, force)
    if not trig["triggered"]:
        ev = Event(
            id=_new_id(), agent="nova", event_type="scan_skipped",
            timestamp=now, aoi=aoi, status="ok",
            message=f"Nova checked {aoi.title()} — no trigger, scan skipped.",
            payload={"trigger": trig},
        )
        events.add(ev)
        return {"triggered": False, "event": ev.model_dump(mode="json")}

    features = _scan_sites(aoi, live)
    summary = store.upsert(features, now=now, aoi=aoi)
    scanned = len(features)  # this AOI's site count (summary['total'] is store-wide)

    hhmm = now.strftime("%H:%M")
    msg = (
        f"Nova ran at {hhmm} — scanned {aoi.title()} (high-res), "
        f"{scanned} active sites "
        f"({summary['new']} new, {summary['updated']} re-confirmed)."
    )
    ev = Event(
        id=_new_id(), agent="nova", event_type="run_completed",
        timestamp=now, aoi=aoi, status="ok", message=msg,
        payload={
            "mode": "live" if live else "demo",
            "trigger": trig,
            "sites": scanned,
            "new": summary["new"],
            "updated": summary["updated"],
            "store_total": summary["total"],
            "method": "highres-structural-change",
        },
    )
    events.add(ev)
    return {"triggered": True, **summary, "event": ev.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="nova-loop",
        description="Nova's autonomous detection loop.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--aoi", default="karrada", choices=list(AOI_PRESETS),
                        help="AOI preset (default: karrada)")
    parser.add_argument("--once", action="store_true",
                        help="run a single cycle and exit")
    parser.add_argument("--interval", type=float, default=60.0,
                        help="seconds between cycles when looping (default: 60)")
    parser.add_argument("--live", action="store_true",
                        help="run a real GEE/Wayback scan instead of replaying "
                             "the cached high-res result")
    parser.add_argument("--force", action="store_true",
                        help="bypass the Sentinel trigger (and GEE) — always scan. "
                             "Used when hosted without GEE credentials.")
    args = parser.parse_args()

    mode = "live" if args.live else "demo"

    def cycle(n: int) -> None:
        res = run_cycle(args.aoi, live=args.live, force=args.force)
        if res.get("triggered"):
            print(f"  cycle {n}: {res['total']} sites "
                  f"({res['new']} new, {res['updated']} re-confirmed)")
        else:
            print(f"  cycle {n}: no trigger, skipped")

    print(f"Nova autonomous loop — aoi={args.aoi} mode={mode}")
    if args.once:
        cycle(1)
        return

    print(f"  running every {args.interval:g}s — Ctrl-C to stop")
    n = 0
    try:
        while True:
            n += 1
            cycle(n)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n  stopped.")


if __name__ == "__main__":
    main()
