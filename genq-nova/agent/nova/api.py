"""
Nova FastAPI layer.

Serves the unified signal store and the agent event log to the frontend, and
exposes a stubbed Nova run trigger so the demo shows Nova behaving like a live
agent rather than a static map.

Endpoints:
    GET  /                  service info
    GET  /signals           all signals (GeoJSON FeatureCollection)
    GET  /signals/{agent}   one source's signals (GeoJSON)
    GET  /detections        Nova's raw CV detections — polygons + deltas (GeoJSON)
    GET  /footprints        existing building footprints base layer (GeoJSON)
    GET  /events            agent event log (JSON), ?agent= &limit=
    GET  /summary           counts by source + latest run (JSON)
    POST /nova/run          stubbed Nova run — appends a fresh event, returns it

Run:
    GEE not required. Populate the store first:
        python -m nova.run && python -m nova.generate
    Then:
        python -m nova.api          # uvicorn on :8000
        nova-api

Reads from SQLite (nova.db) as the single source of truth; /detections reads the
canonical detections_karrada.geojson for full polygon + delta detail.
"""

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from nova.esri import esri_crop
from nova.signals import (
    AGENT_LAYER,
    DATA_DIR,
    SignalStore,
    signals_to_geojson,
)
from nova.events import EventStore, make_nova_run_event, seed_events

THUMB_CACHE = DATA_DIR / "cache" / "thumbs"

_signals = SignalStore()
_events = EventStore()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Ensure the event log is seeded before serving."""
    _events.init_db()
    n = seed_events(_events)
    if n:
        print(f"  seeded {n} events into the log")
    yield


app = FastAPI(
    title="Nova API",
    description="GENQ geo-intelligence signal store + agent event log",
    version="0.1.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # prototype: open for the local Next.js dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

def _require_signals() -> SignalStore:
    """Guard: the store must be populated (run nova.run + nova.generate first)."""
    if not _signals.db_path.exists() or not _signals.counts_by_agent():
        raise HTTPException(
            status_code=503,
            detail="Signal store is empty. Run: python -m nova.run && python -m nova.generate",
        )
    return _signals


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
def root() -> dict:
    return {
        "service": "Nova API",
        "status": "ok",
        "endpoints": [
            "/signals", "/signals/{agent}", "/detections", "/footprints",
            "/events", "/summary", "POST /nova/run",
        ],
    }


@app.get("/signals")
def get_signals() -> dict:
    return signals_to_geojson(_require_signals().all())


@app.get("/signals/{agent}")
def get_signals_for_agent(agent: str) -> dict:
    if agent not in AGENT_LAYER:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown agent '{agent}'. Valid: {', '.join(AGENT_LAYER)}",
        )
    return signals_to_geojson(_require_signals().by_agent(agent))


_DETECTION_SETS = {
    "full": "detections_karrada.geojson",
    "inland": "detections_karrada_inland.geojson",
    "recent": "detections_karrada_recent.geojson",
    "highres": "detections_karrada_v2.geojson",
}


@app.get("/detections")
def get_detections(set: str = "full") -> dict:
    """
    Nova's detections.

    The v1 sets are 10m optical change polygons (ΔNDVI/ΔNDBI/area). The highres
    set is the *validated* v2 method — site centroids from ~0.5m structural-change
    detection. (See docs/methodology.md: v1 is superseded by v2.)

    ?set=full     (default) v1 2022→2024 canonical polygons
    ?set=inland             v1 canonical set, riverbank excluded
    ?set=recent             v1 2023→2026 comparison polygons
    ?set=highres            v2 high-resolution structural-change sites (points)
    """
    if set not in _DETECTION_SETS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown set '{set}'. Valid: {', '.join(_DETECTION_SETS)}",
        )
    path = DATA_DIR / _DETECTION_SETS[set]
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Detection set '{set}' not found at {path.name}. "
                   "Run: python -m nova.run",
        )
    return json.loads(path.read_text())


_FOOTPRINT_SETS = {
    "karrada": "footprints/karrada.min.geojson",
}


@app.get("/footprints")
def get_footprints(aoi: str = "karrada") -> dict:
    """
    Existing building footprints for an AOI — the base "all buildings" map layer.

    These are Microsoft Global ML Building Footprints (a single snapshot, ~24k
    polygons over Karrada), slimmed for the web. They are *context*, not a Nova
    detection: the map stages as base → buildings → Nova changes → agent signals,
    so an analyst sees every building first, then what Nova flags as changed.
    """
    if aoi not in _FOOTPRINT_SETS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown AOI '{aoi}'. Valid: {', '.join(_FOOTPRINT_SETS)}",
        )
    path = DATA_DIR / _FOOTPRINT_SETS[aoi]
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Footprints for '{aoi}' not found at {path.name}. "
                   "Run: python scripts/slim_footprints.py",
        )
    return json.loads(path.read_text())


@app.get("/thumbnail")
def get_thumbnail(lat: float, lon: float) -> Response:
    """
    256x256 Esri World Imagery crop centred exactly on (lat, lon) — the
    high-resolution view of a signal's location. Cached to disk so repeat
    clicks are instant. Visual confirmation only, not a detection source.
    """
    THUMB_CACHE.mkdir(parents=True, exist_ok=True)
    path = THUMB_CACHE / f"{lat:.5f}_{lon:.5f}.png"
    if not path.exists():
        img = esri_crop(lat, lon)
        if img is None:
            raise HTTPException(status_code=502, detail="Esri imagery unavailable")
        img.save(path)
    return Response(
        content=path.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/events")
def get_events(agent: str | None = None, limit: int = 50) -> dict:
    if agent and agent not in AGENT_LAYER:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown agent '{agent}'. Valid: {', '.join(AGENT_LAYER)}",
        )
    evs = _events.list(agent=agent, limit=limit)
    return {"count": len(evs), "events": [e.model_dump(mode="json") for e in evs]}


@app.get("/summary")
def get_summary() -> dict:
    store = _require_signals()
    counts = store.counts_by_agent()
    last_run = _events.latest(agent="nova")
    last_event = _events.latest()
    return {
        "total_signals": sum(counts.values()),
        "by_source": counts,
        "layers": AGENT_LAYER,
        "last_nova_run": last_run.model_dump(mode="json") if last_run else None,
        "last_event": last_event.model_dump(mode="json") if last_event else None,
    }


@app.post("/nova/run")
def trigger_nova_run() -> dict:
    """
    Stubbed Nova run for the demo. Does NOT call Earth Engine; it reports the
    current canonical detection counts as a fresh run and appends an event to
    the log so the UI shows live agent activity.
    """
    store = _require_signals()
    nova_sigs = store.by_agent("nova")
    type_counts: dict[str, int] = {}
    for s in nova_sigs:
        type_counts[s.signal_type] = type_counts.get(s.signal_type, 0) + 1

    event = make_nova_run_event(datetime.now(tz=timezone.utc), type_counts)
    _events.add(event)
    return {
        "status": "completed",
        "stub": True,
        "detections": sum(type_counts.values()),
        "event": event.model_dump(mode="json"),
    }


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
