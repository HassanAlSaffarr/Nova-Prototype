"""
One autonomous Nova cycle, shaped for a hosted (CI) runner.

Runs a real high-res Wayback scan + CNN classify + idempotent upsert for one AOI,
with the Sentinel trigger forced (no GEE credentials needed on the host). Prints
a one-line summary and exposes it as `commit_message` for the GitHub Actions
workflow, so the resulting commit *is* the run's event-log entry.

Usage:  NOVA_AOI=karrada agent/.venv/bin/python scripts/hosted_cycle.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

from nova.loop import run_cycle  # noqa: E402

# Rotate AOIs across the day so each is refreshed even though one cycle scans one
# AOI: 00:00 & 12:00 UTC -> karrada, 06:00 & 18:00 -> bismayah.
ROTATION = ["karrada", "bismayah"]


def pick_aoi() -> str:
    if os.environ.get("NOVA_AOI"):
        return os.environ["NOVA_AOI"]
    hour = datetime.now(tz=timezone.utc).hour
    return ROTATION[(hour // 6) % len(ROTATION)]


def main() -> None:
    aoi = pick_aoi()
    print(f"Hosted cycle starting — aoi={aoi} (live, forced trigger)")
    res = run_cycle(aoi, live=True, force=True)

    if res.get("triggered"):
        msg = (
            f"chore(nova): autonomous cycle — {aoi}: "
            f"{res['new']} new, {res['updated']} re-confirmed ({res['total']} sites)"
        )
    else:
        msg = f"chore(nova): autonomous cycle — {aoi}: no trigger, scan skipped"
    print(msg)

    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as fh:
            fh.write(f"commit_message={msg}\n")
            fh.write(f"aoi={aoi}\n")


if __name__ == "__main__":
    main()
