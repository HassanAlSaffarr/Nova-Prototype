"""
Agent event log — the heartbeat of the GENQ system.

A small append-only log of agent runs ("Nova scanned Karrada at 09:00, detected
50 changes"). Lives in the same nova.db as signals but in its own `events`
table, so regenerating signals (which resets the signals table) never wipes the
log. Seeded with a realistic multi-agent history; POST /nova/run appends to it.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field

from nova.signals import DB_PATH, SignalStore, AGENT_LABEL

# Demo "now" — matches the synthetic agents' clock
NOW = datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc)


class Event(BaseModel):
    id: str
    agent: str                              # nova / roberto / namroud / peter / data_chef
    event_type: str                         # run_completed, synthesis_completed, …
    timestamp: datetime
    aoi: str
    message: str
    status: str = "ok"
    payload: dict = Field(default_factory=dict)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,
    agent       TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    aoi         TEXT NOT NULL,
    message     TEXT NOT NULL,
    status      TEXT NOT NULL,
    payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);
"""


class EventStore:
    """SQLite-backed append-only event log (shares nova.db with signals)."""

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def add(self, e: Event) -> Event:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?)",
                (e.id, e.agent, e.event_type, e.timestamp.isoformat(),
                 e.aoi, e.message, e.status, json.dumps(e.payload)),
            )
        return e

    def _row(self, r: sqlite3.Row) -> Event:
        return Event(
            id=r["id"], agent=r["agent"], event_type=r["event_type"],
            timestamp=datetime.fromisoformat(r["timestamp"]), aoi=r["aoi"],
            message=r["message"], status=r["status"],
            payload=json.loads(r["payload"]),
        )

    def list(self, agent: Optional[str] = None, limit: int = 50) -> list[Event]:
        sql = "SELECT * FROM events"
        params: tuple = ()
        if agent:
            sql += " WHERE agent=?"
            params = (agent,)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params = params + (limit,)
        with self._connect() as conn:
            return [self._row(r) for r in conn.execute(sql, params).fetchall()]

    def latest(self, agent: Optional[str] = None) -> Optional[Event]:
        rows = self.list(agent=agent, limit=1)
        return rows[0] if rows else None

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]


# ---------------------------------------------------------------------------
# Event construction + seeding
# ---------------------------------------------------------------------------


def _new_id() -> str:
    return f"evt-{uuid.uuid4()}"


def make_nova_run_event(
    timestamp: datetime,
    counts: dict,
    *,
    aoi: str = "karrada",
) -> Event:
    """Build a 'Nova scanned X, detected N changes' event from type counts."""
    total = sum(counts.values())
    confirmed = counts.get("confirmed_change", 0)
    candidate = counts.get("candidate_change", 0)
    hhmm = timestamp.strftime("%H:%M")
    return Event(
        id=_new_id(),
        agent="nova",
        event_type="run_completed",
        timestamp=timestamp,
        aoi=aoi,
        message=(
            f"Nova ran at {hhmm} — scanned {aoi.title()}, detected {total} "
            f"changes ({confirmed} confirmed, {candidate} candidate)."
        ),
        payload={
            "detections": total,
            "confirmed_change": confirmed,
            "candidate_change": candidate,
            "duration_s": 41,
        },
    )


def seed_events(store: EventStore, *, force: bool = False) -> int:
    """Seed a realistic multi-agent run history. No-op if events already exist
    (unless force=True). Reads current signal counts so the numbers match."""
    store.init_db()
    if store.count() > 0 and not force:
        return 0

    sig_counts = SignalStore().counts_by_agent()

    # Nova's by-type split, for run messages
    nova_sigs = SignalStore().by_agent("nova")
    nova_types: dict[str, int] = {}
    for s in nova_sigs:
        nova_types[s.signal_type] = nova_types.get(s.signal_type, 0) + 1

    events: list[Event] = []

    # Three days of history. Nova runs twice a day; the support agents run once
    # a day; Data Chef runs after them.
    support = {
        "roberto": ("Roberto", "collected", "survey signals"),
        "namroud": ("Namroud", "ingested", "institutional records"),
        "peter": ("Peter", "processed", "social signals"),
    }

    for day in range(3, 0, -1):
        base = NOW - timedelta(days=day)

        # Nova morning + evening run
        for hour in (8, 20):
            ts = base.replace(hour=hour, minute=15)
            events.append(make_nova_run_event(ts, nova_types))

        # Support agents mid-morning
        for i, (agent, (label, verb, noun)) in enumerate(support.items()):
            ts = base.replace(hour=10, minute=5 + i * 7)
            n = sig_counts.get(agent, 0)
            events.append(Event(
                id=_new_id(), agent=agent, event_type="run_completed",
                timestamp=ts, aoi="karrada",
                message=f"{label} {verb} {n} {noun} across Karrada.",
                payload={"signals": n},
            ))

        # Data Chef synthesis in the afternoon
        ts = base.replace(hour=14, minute=30)
        n_chef = sig_counts.get("data_chef", 0)
        events.append(Event(
            id=_new_id(), agent="data_chef", event_type="synthesis_completed",
            timestamp=ts, aoi="karrada",
            message=f"Data Chef synthesized {n_chef} cross-source insights from "
                    f"the latest agent outputs.",
            payload={"insights": n_chef},
        ))

    # One most-recent Nova run, a few hours before 'now'
    events.append(make_nova_run_event(NOW - timedelta(hours=3), nova_types))

    for e in events:
        store.add(e)
    return len(events)
