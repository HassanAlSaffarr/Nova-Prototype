"""
Nova synthetic-intelligence orchestrator.

Loads Nova's CV detections, runs the four synthetic agents over them (some of
their output anchored near Nova sites), runs Data Chef to synthesize cross-source
clusters, writes everything to the unified SQLite store, and exports GeoJSON.

Usage:
    python -m nova.generate          # rebuild the full signal set
    nova-generate

Requires Nova detections first:  python -m nova.run
"""

import sys

from nova.signals import (
    SignalStore,
    export_geojson,
    load_nova_signals,
)
from nova.agents import roberto, namroud, peter, data_chef


def build_all() -> SignalStore:
    print("Loading Nova detections...")
    try:
        nova = load_nova_signals()
    except FileNotFoundError as exc:
        sys.exit(str(exc))
    print(f"  {len(nova)} Nova signals")

    print("Running synthetic agents...")
    rob = roberto.generate(nova)
    nam = namroud.generate(nova)
    pet = peter.generate(nova)
    print(f"  Roberto {len(rob)} | Namroud {len(nam)} | Peter {len(pet)}")

    base = nova + rob + nam + pet
    print("Running Data Chef synthesis...")
    chef = data_chef.generate(base)
    print(f"  Data Chef {len(chef)} synthesis insights")

    all_signals = base + chef

    store = SignalStore()
    store.init_db(reset=True)
    n = store.insert_many(all_signals)
    print(f"\nStored {n} signals in {store.db_path}")

    paths = export_geojson(store)
    print("Exported GeoJSON:")
    for p in paths:
        print(f"  {p}")

    return store


def _summary(store: SignalStore) -> None:
    counts = store.counts_by_agent()
    print("\n" + "=" * 50)
    print("  Signal counts by source")
    print("=" * 50)
    for agent in ["nova", "roberto", "namroud", "peter", "data_chef"]:
        print(f"  {agent:<12} {counts.get(agent, 0):>4}")
    print(f"  {'TOTAL':<12} {sum(counts.values()):>4}")

    chef = store.by_agent("data_chef")
    if chef:
        print("\n  Top Data Chef insights:")
        for d in chef[:5]:
            print(f"    conf={d.confidence:.2f}  {d.title_en}")
            print(f"      {d.summary[:110]}...")


def main() -> None:
    store = build_all()
    _summary(store)
    print("\nDone.")


if __name__ == "__main__":
    main()
