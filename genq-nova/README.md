# GENQ — Nova Agent Prototype

Nova is GENQ's **geo-mapping intelligence agent**: it detects new construction and
building changes across Iraq from satellite imagery — including projects with no
online footprint — and projects them, fused with the other agents' signals, onto
one market-intelligence map of Baghdad (Karrada for the prototype).

- **How detection works:** [docs/methodology.md](docs/methodology.md)
- **Where it's going:** [docs/roadmap.md](docs/roadmap.md)

---

## Detection methods: v1 (superseded) → v2 (current)

The method was rebuilt mid-prototype. Both are still in the tree and both are
selectable in the demo, but **v2 is the validated, canonical method**; v1 is kept
for the falsification story (see methodology).

| | v1 — optical indices | v2 — high-res structural change |
|---|---|---|
| Data | 10 m Sentinel-2 | ~0.5 m Esri Wayback |
| Signal | ΔNDVI / ΔNDBI / ΔMNDWI | image-gradient "structure" appearing on bare land |
| Status | **superseded** (NDBI bare-soil confusion in arid Baghdad) | **current** (~6× Bismayah/Karrada discrimination on ground truth) |

## Code map (`agent/nova/`)

**v2 — current detector + pipeline**
- `highres.py` — high-resolution structural-change detector (the core)
- `sar.py` — Sentinel-1 backscatter, the cheap coarse *trigger*
- `esri.py` — Esri World Imagery / Wayback tile helpers (before/after crops)
- `verify.py` — Tier-3 internet/permit corroboration (one-directional)
- `detection_store.py` — idempotent, lifecycle-tracking store of live sites
- `loop.py` — the autonomous loop (trigger → scan → upsert → log)

**v1 — superseded optical-index detector** (still served for the method story)
- `change_detection.py` — Sentinel-2 NDVI/NDBI/MNDWI differencing
- `detections.py` — Detection model + deterministic IDs
- `run.py` — v1 end-to-end CLI

**Shared infrastructure**
- `config.py` — AOI presets, CRS, data paths (single source of truth)
- `footprints.py` — Microsoft ML Building Footprints loader (→ buildings layer)
- `signals.py` — Signal model + SQLite store (the four synthetic agents)
- `events.py` — append-only agent event log
- `generate.py` — synthetic agent data (Roberto / Namroud / Peter / Data Chef)
- `api.py` — FastAPI layer the web app reads
- `explore.py`, `visualize.py`, `visualize_bands.py` — GEE preview + sample art

## Data map (`agent/data/`)

| File | Method | Tracked? |
|---|---|---|
| `detections_karrada{,_inland,_recent}.geojson` | v1 polygons | yes |
| `detections_karrada_v2.geojson`, `detections_bismayah_v2.geojson` | v2 sites | yes |
| `detections_live.geojson` | v2, written by the loop | no (runtime) |
| `footprints/karrada.min.geojson` | buildings base layer (slimmed) | yes |
| `footprints/karrada.geojson` | raw MS source | no (large) |
| `nova.db` | signals + events (SQLite) | no (regenerable) |

`scripts/` holds the derive-once helpers: `slim_footprints.py` (raw → served
footprints), `bake_v2_ids.py` (stamp v2 sites with stable ids), `test_loop.py`
(loop smoke test).

> **Note on organisation.** v1 and v2 modules share `agent/nova/` rather than
> living in `v1/` / `v2/` subpackages: a physical split touches every import in
> `api.py`/`run.py` and the served file paths, so it's deferred to a post-demo
> refactor to keep the working demo stable. The v1/v2 split is documented above
> and in each module's docstring.

---

## Running it

```bash
# from agent/ (with the project venv)
python -m nova.run            # v1 pipeline → detections geojson
python -m nova.generate       # synthetic agent signals → nova.db
python -m nova.loop --once    # one autonomous v2 cycle (demo mode, no GEE)
python -m nova.api            # FastAPI on :8000

# from web/
npm run dev                   # Next.js + MapLibre + deck.gl on :3000
```

The map opens on the validated v2 detector over the buildings base layer; the
layer panel switches methods and toggles each agent's signals.
