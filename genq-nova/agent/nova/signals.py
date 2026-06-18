"""
Shared signal envelope + SQLite store for all five GENQ sources.

Every source — Nova (CV change detection) and the four synthetic agents
(Roberto, Namroud, Peter, Data Chef) — emits the same `Signal` shape, so the
map and FastAPI layer can treat them uniformly. Source-specific fields live in
`payload`. Nova's raster Detections are adapted into this envelope too.

Storage: one SQLite table `signals` (source_agent column distinguishes them)
plus per-layer GeoJSON exports for the map.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from nova.config import DATA_DIR

DB_PATH = DATA_DIR / "nova.db"
SIGNALS_GEOJSON_DIR = DATA_DIR / "signals"

SourceAgent = Literal["nova", "roberto", "namroud", "peter", "data_chef"]

# Agent → GENQ data layer (see CLAUDE.md). Used by the map legend / filters.
AGENT_LAYER: dict[str, str] = {
    "nova": "Geo-mapping",
    "roberto": "Survey Intelligence",
    "namroud": "Institutional Data",
    "peter": "Social Listening",
    "data_chef": "Expert Analysis",
}

AGENT_LABEL: dict[str, str] = {
    "nova": "Nova",
    "roberto": "Roberto",
    "namroud": "Namroud",
    "peter": "Peter",
    "data_chef": "Data Chef",
}


class Signal(BaseModel):
    """One geo-located intelligence signal from any GENQ source."""

    id: str
    source_agent: SourceAgent
    layer: str
    signal_type: str                       # source-specific subtype
    lat: float
    lon: float
    title_en: str
    title_ar: str
    summary: str
    value: Optional[float] = None          # headline numeric (price, count, sentiment…)
    unit: Optional[str] = None             # e.g. "USD", "IQD/month", "%"
    confidence: float                      # 0.0 – 1.0
    timestamp: datetime
    geometry: dict                         # GeoJSON geometry (WGS84)
    payload: dict = Field(default_factory=dict)
    related_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Nova Detection → Signal adapter
# ---------------------------------------------------------------------------


def detection_feature_to_signal(feat: dict) -> Signal:
    """Adapt one feature from detections_karrada.geojson into a Signal."""
    p = feat["properties"]
    dtype = p["detection_type"]
    title_en = (
        "Confirmed change detected" if dtype == "confirmed_change"
        else "Candidate change detected"
    )
    title_ar = (
        "رصد تغيّر مؤكَّد" if dtype == "confirmed_change"
        else "رصد تغيّر محتمل"
    )
    area = p.get("area_m2", 0.0)
    return Signal(
        id=p["id"],
        source_agent="nova",
        layer=AGENT_LAYER["nova"],
        signal_type=dtype,
        lat=p["lat"],
        lon=p["lon"],
        title_en=title_en,
        title_ar=title_ar,
        summary=(
            f"Satellite change detection flagged a {area:,.0f} m² site between "
            f"the 2022 and 2024 summer composites "
            f"(ΔNDBI {p.get('delta_ndbi')}, ΔNDVI {p.get('delta_ndvi')})."
        ),
        value=round(area, 0),
        unit="m²",
        confidence=p["confidence"],
        timestamp=datetime.fromisoformat(p["detected_at"]),
        geometry=feat["geometry"],
        payload={
            "delta_ndvi": p.get("delta_ndvi"),
            "delta_ndbi": p.get("delta_ndbi"),
            "delta_brightness": p.get("delta_brightness"),
            "overlaps_footprint": p.get("overlaps_footprint"),
        },
    )


def load_nova_signals() -> list[Signal]:
    """Load the canonical Nova detections and adapt them to Signals."""
    path = DATA_DIR / "detections_karrada.geojson"
    if not path.exists():
        raise FileNotFoundError(
            f"Nova detections not found at {path}. Run: python -m nova.run"
        )
    fc = json.loads(path.read_text())
    return [detection_feature_to_signal(f) for f in fc["features"]]


# ---------------------------------------------------------------------------
# SQLite store
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id            TEXT PRIMARY KEY,
    source_agent  TEXT NOT NULL,
    layer         TEXT NOT NULL,
    signal_type   TEXT NOT NULL,
    lat           REAL NOT NULL,
    lon           REAL NOT NULL,
    title_en      TEXT NOT NULL,
    title_ar      TEXT NOT NULL,
    summary       TEXT NOT NULL,
    value         REAL,
    unit          TEXT,
    confidence    REAL NOT NULL,
    timestamp     TEXT NOT NULL,
    geometry      TEXT NOT NULL,   -- JSON
    payload       TEXT NOT NULL,   -- JSON
    related_ids   TEXT NOT NULL    -- JSON array
);
CREATE INDEX IF NOT EXISTS idx_signals_agent ON signals(source_agent);
CREATE INDEX IF NOT EXISTS idx_signals_layer ON signals(layer);
"""


class SignalStore:
    """Thin SQLite wrapper for the unified signals table."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self, *, reset: bool = False) -> None:
        with self._connect() as conn:
            if reset:
                conn.execute("DROP TABLE IF EXISTS signals")
            conn.executescript(_SCHEMA)

    def insert_many(self, signals: list[Signal]) -> int:
        rows = [
            (
                s.id, s.source_agent, s.layer, s.signal_type, s.lat, s.lon,
                s.title_en, s.title_ar, s.summary, s.value, s.unit,
                s.confidence, s.timestamp.isoformat(),
                json.dumps(s.geometry), json.dumps(s.payload),
                json.dumps(s.related_ids),
            )
            for s in signals
        ]
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO signals VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
        return len(rows)

    def _row_to_signal(self, r: sqlite3.Row) -> Signal:
        return Signal(
            id=r["id"], source_agent=r["source_agent"], layer=r["layer"],
            signal_type=r["signal_type"], lat=r["lat"], lon=r["lon"],
            title_en=r["title_en"], title_ar=r["title_ar"], summary=r["summary"],
            value=r["value"], unit=r["unit"], confidence=r["confidence"],
            timestamp=datetime.fromisoformat(r["timestamp"]),
            geometry=json.loads(r["geometry"]), payload=json.loads(r["payload"]),
            related_ids=json.loads(r["related_ids"]),
        )

    def all(self) -> list[Signal]:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM signals ORDER BY confidence DESC")
            return [self._row_to_signal(r) for r in cur.fetchall()]

    def by_agent(self, agent: str) -> list[Signal]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM signals WHERE source_agent=? ORDER BY confidence DESC",
                (agent,),
            )
            return [self._row_to_signal(r) for r in cur.fetchall()]

    def counts_by_agent(self) -> dict[str, int]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT source_agent, COUNT(*) n FROM signals GROUP BY source_agent"
            )
            return {r["source_agent"]: r["n"] for r in cur.fetchall()}


# ---------------------------------------------------------------------------
# GeoJSON export
# ---------------------------------------------------------------------------


def signals_to_geojson(signals: list[Signal]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": s.geometry,
                "properties": {
                    "id": s.id,
                    "source_agent": s.source_agent,
                    "layer": s.layer,
                    "signal_type": s.signal_type,
                    "title_en": s.title_en,
                    "title_ar": s.title_ar,
                    "summary": s.summary,
                    "value": s.value,
                    "unit": s.unit,
                    "confidence": s.confidence,
                    "timestamp": s.timestamp.isoformat(),
                    "related_ids": s.related_ids,
                    "lat": s.lat,
                    "lon": s.lon,
                    **s.payload,
                },
            }
            for s in signals
        ],
    }


def export_geojson(store: SignalStore) -> list[Path]:
    """Write one combined signals.geojson + one per agent. Returns paths."""
    SIGNALS_GEOJSON_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    combined = SIGNALS_GEOJSON_DIR / "signals_all.geojson"
    combined.write_text(json.dumps(signals_to_geojson(store.all()), indent=2))
    written.append(combined)

    for agent in AGENT_LAYER:
        sigs = store.by_agent(agent)
        if not sigs:
            continue
        path = SIGNALS_GEOJSON_DIR / f"signals_{agent}.geojson"
        path.write_text(json.dumps(signals_to_geojson(sigs), indent=2))
        written.append(path)

    return written
