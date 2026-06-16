# GENQ — Nova Agent Prototype

## What this is
Prototype of the "Nova" agent for GENQ (gen-q.ai), an Iraqi market intelligence platform. Nova is the geo-mapping intelligence agent — it ingests satellite imagery + outputs from other agents and projects everything onto an interactive map of Iraq.

## Deadline
Saturday June 20, 2026. ~4 working days. Demo must be polished and demoable end-to-end. Do not overscope.

## What we are building

**Agent loop (Python, the centerpiece):**
- Pulls Sentinel-2 imagery over one Baghdad AOI (Karrada) via Google Earth Engine
- Loads Microsoft Global ML Building Footprints filtered to the AOI
- Detects changes between two dates using footprint comparison + raster band diff (NDVI, NDBI)
- Emits structured detection events with lat/lon, timestamp, change type, confidence
- Generates synthetic outputs from four mock agents: Roberto (surveys), Namroud (institutional/financial), Peter (social), Data Chef (synthesis)
- Writes all outputs to SQLite + GeoJSON
- Exposes data via FastAPI
- Runs on a scheduler with an event log

**Map UI (Next.js + MapLibre + deck.gl):**
- Landing view: full Iraq map, low signal density
- Zoom into Karrada AOI → rich signal overlay
- Click pin → side panel with structured detail + before/after satellite crop for CV-detected items
- Filter UI by signal type, source agent, date
- Event log panel showing recent Nova runs
- Dark theme matching GENQ brand

## What we are NOT building
- Custom CV model training
- Live web scraping
- Production deployment hardening
- Multi-language NLP
- Real-time pipelines (scheduler intervals are short for demo purposes)
- Authentication / user accounts
- Multiple Iraqi cities (Baghdad / Karrada only)
- Natural-language query bar
- Tests until something is stable

## Tech stack
- Python 3.11+, FastAPI, `earthengine-api`, geemap, geopandas, shapely, rasterio, APScheduler, SQLite, pydantic
- Google Earth Engine (Sentinel-2 SR Harmonised collection) — free tier, non-commercial use acknowledged as production decision deferred
- Microsoft Global ML Building Footprints (loaded as GEE FeatureCollection or downloaded GeoJSON filtered to Karrada)
- Next.js 14 (app router), TypeScript, Tailwind, MapLibre GL JS, deck.gl

## Operating principles
- Plans live in chat with Hassan, not in files. Do not create PLAN.md or similar plan documents unless explicitly asked.
- Build the agent loop end-to-end on Karrada first; treat the AOI as a config value so adding more later is trivial
- No custom CV training — use Microsoft footprints + raster band diff
- Sentinel-2 is 10m resolution; do not promise classification of building types
- Synthetic data for the other 4 agents must be realistic: Arabic + English place names, plausible Baghdad coordinates, plausible values
- Commit frequently; main should always run
- When ambiguity arises, surface it as a question rather than guessing
- When Hassan needs to make a decision (date selection, schema design, library choice), surface it explicitly with options + your recommendation. Don't silently pick.
- If you spot scope creep, push back.

## Reference materials
- GENQ website: https://gen-q.ai
- Nova's official scope (from website): "Spatial mapping of data and information. Jobs. Prices. Real estate. Tenders. Automated." Capabilities: Location-based Data, Spatial Positioning, Geographic Analytics, Real-Time Mapping.
- GENQ's 5 agents: Roberto (Survey), Namroud (Institutional), Peter (Digital Listening), Nova (Geo-mapping), Data Chef (Synthesis)
- GENQ's 5 data layers: Survey Intelligence, Institutional Data, Social Listening, Web Intelligence, Expert Analysis