# Nova — Full Project Log

A complete record of the Nova prototype: what it is, every major decision and why,
obstacles hit and how they were resolved, outputs produced, and the honest state of
the system. Written for data collection / retrospective.

- **Product:** Nova, the geo-mapping intelligence agent for **GENQ** (gen-q.ai), an
  Iraqi market-intelligence platform.
- **Job:** detect new construction / building change across Iraq from satellite
  imagery — *including projects with no online footprint* — and project them, fused
  with other agents' signals, onto one interactive map.
- **Prototype scope:** Karrada (central Baghdad) + Bismayah (new city, SE Baghdad).
- **Window:** 2026-06-16 → 2026-06-20. 45 commits.
- **Stack:** Python 3.12, FastAPI, Google Earth Engine, Esri World Imagery Wayback,
  Microsoft ML Building Footprints, SQLite; Next.js 14 + MapLibre + deck.gl + Zustand.

---

## 1. Timeline (phases)

| Phase | Dates | What |
|---|---|---|
| 0. Scaffold | Jun 16 | Repo + project structure |
| 1. v1 pipeline | Jun 17 | Sentinel-2 NDVI/NDBI/MNDWI change detection, MS footprints, CLI |
| 2. Synthetic agents + API | Jun 17 | 4 mock agents, SQLite store, FastAPI, event log |
| 3. Config + viz + sets | Jun 18 | Centralised config, sample artifacts, recent/inland detection sets, deterministic IDs |
| 4. Frontend | Jun 19 | Next.js map, side panel, event log, layer filter, polish |
| 5. **Methodology pivot (v2)** | Jun 19–20 | Falsified v1; built high-res structural-change detector |
| 6. Tiers: verify + autonomy | Jun 20 | Internet verification, idempotent autonomous loop |
| 7. Map integration | Jun 20 | Buildings base layer, v2 wired + default, AOI switcher → simultaneous AOIs |
| 8. Realism + honesty pass | Jun 20 | Precision filter, river-detection tagging, size-floor tuning, before/after panel, event-log accuracy |

---

## 2. The central story: change-detection methodology (v1 → v2)

### v1 — 10 m optical indices (Jun 17, later SUPERSEDED)
- **Method:** difference NDVI (vegetation), NDBI (built-up), MNDWI (water) between two
  dated Sentinel-2 composites; flag pixels where vegetation fell and built-up rose.
- **Tuning adopted:** ΔNDBI ≥ 0.10, min area ≥ 1000 m². Tigris water masked. Polygon
  centroids computed in UTM (EPSG:32638), not geographic CRS (a real bug, fixed).
- **Why it was abandoned (empirical falsification):**
  - **NDBI confuses new buildings with bare soil** — a documented failure, *worst in
    arid climates*. Baghdad is arid and the Tigris exposes sand/mud banks, so the index
    fired on dried/cleared ground as if it were construction.
  - **Resolution is the root cause:** at 10 m a building is **1–4 noisy pixels**, too
    few to separate from noise. No index or threshold fixes this.
  - Naive **Sentinel-1 SAR** backscatter was also tested and *also failed*: it fired at
    ~15 detections/km² **identically** on Bismayah (a known 100k-unit megaproject) and
    saturated Karrada — discrimination ratio **1.0× (noise)**.
- **Red herring corrected:** an early "94% of detections are near the river → broken"
  metric was wrong. ~98% of the Karrada peninsula's land is within 200 m of the wrapping
  Tigris, so "near-river" is geometry, not bias. Self-corrected.

### v2 — high-resolution structural change (current)
- **Two things changed, not one:**
  1. **Resolution:** 10 m Sentinel-2 → **~0.5 m Esri World Imagery Wayback** (≈190 dated
     versions back to 2014, free, fetched programmatically).
  2. **Signal:** band-math indices → **structural texture**. The detector measures local
     image-gradient magnitude ("structure density"), aggregated into ~10 m cells. A cell
     is flagged when *structure appeared where the ground was smooth/bare before*:
     `(structure_after − structure_before > threshold) AND (structure_before < bare)`.
- **Pipeline:** tile the AOI (~1 km tiles) → run the detector per tile → cluster flagged
  cells into discrete project sites via 8-connected components (BFS, no scipy) → keep
  clusters above a size floor.
- **Validation (ground truth):** flags **~31% of Bismayah** (known active construction)
  vs **~5% of saturated Karrada** — **~6× discrimination**, where 10 m optical and SAR
  managed ~1×. A valid detector must light up where construction is known and stay quiet
  where it isn't; only v2 does.
- **Precision filter:** the texture signal also fires on **river sandbars, exposed banks,
  and busy parking lots** (vehicles add texture). Detections are categorised by proximity
  to a Microsoft building footprint (≤70 m = `construction`, else `land_emergence`).
  Land-emergence is **kept and tagged, not deleted** — new usable riverfront land can be
  commercially relevant; the analyst decides.
- **Honest ceiling:** the classical texture signal **cannot** distinguish "lot full of
  cars/materials" from "lot full of new building." That needs a **CNN building-segmentation
  model** — viable now that imagery is 0.5 m (it was not viable at 10 m), but blocked here
  only because PyTorch/TensorFlow aren't installed (env has numpy + PIL only).

---

## 3. Key measured facts

- **Karrada AOI:** `[44.385, 33.285, 44.430, 33.320]` ≈ **4.2 km × 3.9 km = 16.3 km²**.
- **Bismayah AOI:** `[44.595, 33.175, 44.642, 33.213]`.
- **Full Karrada high-res scan:** **~242 s (~4 min)**, ≈ 15 s/km². Confirmed full
  coverage — raw detections span all four edges of the bbox.
- **Size floor → site count (Karrada, 2023→2026):** the count is purely a floor choice,
  not coverage:

  | Floor | Sites |
  |---|---|
  | ≥1,000 m² | 100 |
  | ≥1,500 m² | 57 |
  | ≥3,000 m² | **17 (chosen)** |
  | ≥5,000 m² | 6 |
  | ≥10,000 m² | 2 |

- **Current demo sets:** Karrada **17** (10 construction + 7 land-emergence) at 3,000 m²;
  Bismayah **80** at 5,000 m².
- **Iraq-scale estimate:** naive full high-res Iraq on one machine ≈ **75 days**. With a
  Sentinel trigger flagging ~2% for high-res confirm ≈ 1.5 days on one machine, or
  **~25 min across 100 cloud workers.** Scaling = trigger + parallelism, not a bigger scan.
- **Validation sites:** Bismayah New City (33.1935, 44.6175) = POSITIVE; Karrada interior
  = NEGATIVE (saturated; a poor change-detection subject — real growth is on city edges).

---

## 4. Architecture: the tiered pipeline

1. **Trigger (cheap, frequent):** Sentinel-1/2 passes flag "something may have changed
   here." High recall, low precision — just narrows where to spend effort.
   *Status: groundwork in `sar.py`; the 5-day cadence is design, not yet wired.*
2. **Confirm (high-res):** pull before/after ~0.5 m Wayback crops, run the structural-change
   detector. *Status: built (`highres.py`), validated.*
3. **Verify (internet):** reverse-geocode (OSM Nominatim) → build a search query → corroborate
   against news/permits/social. **One-directional by design:** online evidence *confirms*;
   absence does *not* refute (many Iraqi projects have no online footprint — the reason Nova
   exists). *Status: built (`verify.py`), demonstrated on Bismayah.*

**Autonomy (`loop.py` + `detection_store.py`):** each cycle = trigger → scan → **idempotent
upsert** → event log. Re-running converges (same site id → update, not duplicate). Per-site
**change lifecycle** tracked: `first_seen / last_seen / times_seen / status`. Demo mode runs
with no GEE (replays the cached high-res result); `--live` runs a real scan.
**Honest limit:** it is autonomous *logic* but runs **on the laptop** — laptop off, no scans.
True 24/7 autonomy needs hosting (cron / cloud). The code is built for that (headless, idempotent).

---

## 5. The 5 GENQ agents (provenance)

- **Nova** — Geo-mapping. **The only REAL data** (satellite-derived).
- **Roberto** — Survey Intelligence (field surveys). **Synthetic.**
- **Namroud** — Institutional / financial records. **Synthetic.**
- **Peter** — Digital / social listening. **Synthetic.**
- **Data Chef** — Synthesis across sources. **Synthetic.**

The four synthetic agents are fabricated locally (`nova/agents/`), anchored near Nova's real
sites with realistic Baghdad place names + plausible values. **Nothing is pulled from any real
source** (no HTTP/scrape/API in the code). They are Karrada-only, so they don't appear on Bismayah.

---

## 6. Obstacles & fixes (chronological)

| Obstacle | Resolution |
|---|---|
| v1 polygon centroids wrong (geographic CRS) | Compute in UTM EPSG:32638 |
| NDBI fires on bare/dried soil (arid) | Root flaw → drove the v2 pivot |
| SAR experiment: empty collection ("no bands") | Karrada is ASCENDING-only (15 scenes); fixed orbit filter |
| "94% near river = broken" | Red herring (peninsula geometry); self-corrected |
| Wayback tile 301 redirects | `follow_redirects=True` |
| Temp filesystem ENOSPC kills scans | `progress=False`; route logs to main disk |
| Full sequential scan too slow (20+ min) | Parallelised mosaic fetch (ThreadPoolExecutor, 16 workers) → ~4 min |
| First full scan: 588 raw Karrada clusters (too many) | Size floor |
| Demo showed falsified v1 detections | Wired v2 in, made it the default |
| Frontend "Can't reach API" + empty event log | **Stale backend** — old process serving pre-change code; restarted |
| **I wrongly deleted river detections** | Restored all; tag `construction` vs `land_emergence` instead of dropping |
| Only 6 Karrada detections looked unrealistic | It was the 5,000 m² floor, not coverage; dropped to 3,000 → 17 |
| Parking-lot false positive (empty → full of vehicles) | Acknowledged honest ceiling; needs CNN |
| land-emergence colour collided with Roberto's cyan | Recoloured slate grey |
| **MS footprints not rendering** | Removed fragile `buildingsZoom` gate (only updated on map-move) |
| Loop event reported store total as one AOI's count ("97") | Report per-AOI scanned count; store total → payload |
| Event log said "detected 50 changes" (v1 wording/counts) | Re-seeded with high-res framing + real per-AOI counts (17/80) |
| One-AOI-at-a-time didn't scale | All AOIs render simultaneously; area buttons → "fly to" |

---

## 7. Outputs

### Backend modules (`agent/nova/`)
- **v2 (current):** `highres.py` (detector + precision filter), `sar.py` (S1 trigger),
  `esri.py` (Wayback tiles), `verify.py` (Tier-3), `detection_store.py` (idempotent store),
  `loop.py` (autonomous loop).
- **v1 (superseded):** `change_detection.py`, `detections.py`, `run.py`.
- **Shared:** `config.py`, `footprints.py`, `signals.py`, `events.py`, `generate.py`,
  `api.py`, `explore.py`, `visualize.py`, `visualize_bands.py`.

### API endpoints (`api.py`)
`/`, `/signals`, `/signals/{agent}`, `/detections?set=…`, `/footprints?aoi=…`,
`/thumbnail` (current crop), `/wayback?lat&lon&date` (before/after crops), `/events`,
`/summary`, `POST /nova/run` (deprecated stub).
- Detection sets: `full` / `inland` / `recent` (v1), `highres` (Karrada v2),
  `highres_bismayah` (Bismayah v2), `live` (loop output).

### Data (`agent/data/`)
- v1: `detections_karrada{,_inland,_recent}.geojson`. v2: `detections_karrada_v2.geojson` (17),
  `detections_bismayah_v2.geojson` (80). `detections_live.geojson` (loop, runtime).
- `footprints/karrada.min.geojson` — 24,340 MS building footprints, slimmed 9.8→5.2 MB.
- `samples/v1/` — Sentinel composites, NDVI/NDBI bands, top-10 crops.
- `samples/v2/` — before/after Wayback crops at detected sites (the v2 evidence).
- `nova.db` — signals (136) + event log (SQLite).

### Frontend (`web/`)
Next.js + MapLibre (CARTO Dark) + deck.gl. All AOIs render at once. Layers: building
footprints base, Nova detections (green = construction, grey = land-emergence rings), 5 agent
point layers. Side panel: before/after Wayback imagery, category, confidence, related signals.
Event log, "Fly to" area buttons, collapsed legacy v1 method picker. Brand: dark navy
`#0a0e1a`, neon green `#00ff9d`, Inter, "NOVA" wordmark.

### Scripts (`scripts/`)
`slim_footprints.py`, `bake_v2_ids.py`, `clean_detections.py`, `rescan_karrada.py`,
`sample_v2_crops.py`, `timed_scan.py`, `test_loop.py`.

---

## 8. Honest standing gaps (not yet done)
1. **True autonomy** — loop runs locally; needs hosting for 24/7.
2. **5-day Sentinel trigger** — design only; runs on a manual `--interval`.
3. **CNN building-segmentation** — the real precision upgrade; blocked on ML deps (torch).
4. **Per-building precision** — current signal can't reject parking-lot/materials false positives.
5. **Physical v1/v2 code split** — documented, not subpackaged (avoided pre-demo import churn).

---

## 9. Full commit history

```
cb7c042  Jun16  scaffold genq-nova project structure
db6bc44  Jun17  Add change detection pipeline: footprints, S2 raster diff, detections, CLI
7b44658  Jun17  footprints: download only Karrada quadkey tile from Azure MS dataset
9450aab  Jun17  fix(change-detection): mask Tigris water, raise min-area, drop expanded_structure
8d3d84b  Jun17  fix(change-detection): compute polygon centroids in UTM, not geographic CRS
4701d8a  Jun17  tune(change-detection): adopt ΔNDBI>=0.10 / min_area>=1000 m2 as canonical
538d434  Jun17  docs: founder-friendly change-detection methodology
8e025f6  Jun17  feat(agents): synthetic intelligence agents + unified signal store
d6fcd30  Jun17  feat(api): FastAPI layer + agent event log
fea1ad6  Jun17  refactor: centralize AOI, CRS, data dir in config.py
d759e47  Jun18  feat(viz): visual sample artifacts
5b4a970  Jun18  feat: recent comparison set (2023 -> 2026)
c3436a5  Jun18  refactor(detections): rename types confirmed_change / candidate_change
8752f35  Jun18  feat(detections): optional riverbank exclusion (inland set)
20db9cc  Jun18  refactor(detections): deterministic IDs from centroid + date hash
cb628cb  Jun18  feat(api): ?set= param on /detections
fb9cb1e  Jun18  feat(viz): spectral band/index renders
b860798  Jun19  feat(web): scaffold Next.js map (CARTO dark + signal layers)
76e67ad  Jun19  feat(web): side panel + related-signal navigation
d2f4f42  Jun19  polish(web): soften AOI + cinematic fly-to
29b3577  Jun19  docs: post-Saturday roadmap
c1dc822  Jun19  feat(web): event log + Run Nova wiring
0f997d5  Jun19  fix(web): remove manual Run Nova button (Nova is autonomous)
2cf2dd8  Jun19  feat(web): side panel polish — Esri thumbnail, provenance
b0a947f  Jun19  feat(web): layer filter + detection-set toggle
138bc20  Jun19  refine(web): compact layer filter + quick isolate
aeaf4c0  Jun19  feat(web): visually differentiate Nova detections
65a71a6  Jun19  feat(web): minimal hover-expand attribution
109090e  Jun19  feat(web): loading / error / empty states
a6bec52  Jun19  feat(detect): Nova v2 high-res structural-change detector
4dda2d6  Jun19  docs(methodology): rewrite for v2, mark v1 superseded
28191c4  Jun19  feat(detect): full-AOI scan + cluster cells into sites
8696d61  Jun20  feat(detect): first full v2 AOI scans + project-size floor
1653569  Jun20  feat(verify): Tier-3 internet corroboration
ce5d95c  Jun20  feat(web): existing-buildings base layer (MS footprints)
9c9366a  Jun20  feat(web): wire validated v2 as selectable Nova method
8f3524d  Jun20  feat(web): default the demo to v2
35fe388  Jun20  feat(agent): autonomous detection loop + idempotent live store
b996376  Jun20  docs(readme): codebase + data map (v1 vs v2)
b54e908  Jun20  refactor(data): separate v1/v2 samples + v2 evidence crops
1088a1a  Jun20  feat(detect): footprint precision-filter + Bismayah AOI
9acd05c  Jun20  feat(web): AOI switcher — Karrada <-> Bismayah
768908b  Jun20  fix(detect): keep river detections, tag construction vs land-emergence
b15be94  Jun20  feat(detect): Karrada at 3,000 m² floor (17 sites) + category colour-coding
1c43ae2  Jun20  feat(web): show all AOIs at once; fix footprints render; declutter
a25fcfb  Jun20  feat(web): before/after Wayback imagery in the side panel
351612b  Jun20  fix(events): event log accurate to high-res method + real counts
```

---

## 10. One-paragraph summary

Nova began as a 10 m Sentinel-2 NDVI/NDBI/MNDWI change detector with a full synthetic-agent
layer, API, and Next.js map. Mid-project that method was **empirically falsified** (NDBI
can't separate new buildings from bare soil at 10 m; SAR gave 1.0× discrimination) and
**replaced** with a high-resolution structural-change detector on free ~0.5 m Esri Wayback
imagery, validated at ~6× discrimination on Bismayah-vs-Karrada ground truth. Around it we
built the intended tiered architecture (Sentinel trigger → high-res confirm → internet
verify), an idempotent autonomous loop with per-site lifecycle, a Microsoft-footprints
precision filter, two simultaneous AOIs, and a before/after-evidence map UI. The remaining
honest gaps are deployment (hosting for true 24/7 autonomy), the real Sentinel trigger
scheduler, and a CNN building classifier for per-building precision — all now viable on the
0.5 m imagery, none yet wired.
