"""
Data Chef — Synthesis (Expert Analysis layer).

Reads every other signal (Nova + Roberto + Namroud + Peter) and finds places
where multiple independent sources cluster together. Each such cluster becomes a
higher-order "insight" signal that links back to its members — the moment that
shows GENQ's value: separate agents independently pointing at the same site.
"""

from collections import Counter

from nova.signals import AGENT_LABEL, AGENT_LAYER, Signal
from nova.agents import _common as c

# A cluster must span this many distinct source agents and total members
_CLUSTER_RADIUS_M = 220.0
_MIN_DISTINCT_AGENTS = 2
_MIN_MEMBERS = 3


def _centroid(sigs: list[Signal]) -> tuple[float, float]:
    return (
        sum(s.lat for s in sigs) / len(sigs),
        sum(s.lon for s in sigs) / len(sigs),
    )


def _cluster(signals: list[Signal]) -> list[list[Signal]]:
    """Greedy spatial clustering. Nova detections seed clusters (they're the
    natural nucleus), then any remaining signal can seed one."""
    used: set[str] = set()
    clusters: list[list[Signal]] = []

    # Seed from Nova first, then everything else, for stable nuclei.
    seeds = [s for s in signals if s.source_agent == "nova"] + \
            [s for s in signals if s.source_agent != "nova"]

    for seed in seeds:
        if seed.id in used:
            continue
        members = [
            s for s in signals
            if s.id not in used
            and c.meters_between(seed.lat, seed.lon, s.lat, s.lon) <= _CLUSTER_RADIUS_M
        ]
        agents = {s.source_agent for s in members}
        if len(members) >= _MIN_MEMBERS and len(agents) >= _MIN_DISTINCT_AGENTS:
            clusters.append(members)
            used.update(s.id for s in members)

    return clusters


def generate(all_signals: list[Signal]) -> list[Signal]:
    """Synthesize cross-source insight signals. `all_signals` should include
    Nova + the three other agents (NOT Data Chef's own output)."""
    out: list[Signal] = []

    for members in _cluster(all_signals):
        lat, lon = _centroid(members)
        agents = sorted({s.source_agent for s in members})
        by_agent = Counter(s.source_agent for s in members)
        has_nova = "nova" in agents
        n = len(members)

        labels = ", ".join(AGENT_LABEL[a] for a in agents)
        area_en, area_ar = c.coarse_area(lat, lon)

        # Confidence rises with corroboration breadth (distinct sources) and
        # depth (member count); a satellite-confirmed cluster gets a small bump.
        # Coefficients kept low so insights spread across ~0.65–0.97, not saturate.
        conf = 0.45 + 0.08 * len(agents) + 0.015 * n + (0.05 if has_nova else 0.0)
        conf = min(conf, 0.97)

        headline = (
            "Emerging development zone" if has_nova
            else "Cross-source activity cluster"
        )
        headline_ar = (
            "منطقة تطوّر ناشئة" if has_nova else "تجمّع نشاط متعدد المصادر"
        )

        breakdown = "; ".join(
            f"{by_agent[a]}× {AGENT_LABEL[a]}" for a in agents
        )
        summary = (
            f"{n} signals from {len(agents)} independent sources ({labels}) "
            f"cluster within {int(_CLUSTER_RADIUS_M)} m in {area_en}. "
            f"Breakdown: {breakdown}. "
            + (
                "Satellite-detected change is corroborated by ground and "
                "institutional signals — a high-confidence growth pocket."
                if has_nova else
                "Multiple non-satellite sources converge here — worth a "
                "satellite re-check."
            )
        )

        out.append(Signal(
            id=c.new_id("data_chef"),
            source_agent="data_chef",
            layer=AGENT_LAYER["data_chef"],
            signal_type="synthesis_insight",
            lat=lat, lon=lon,
            title_en=f"{headline} — {area_en}",
            title_ar=f"{headline_ar} — {area_ar}",
            summary=summary,
            value=float(n), unit="signals",
            confidence=round(conf, 3),
            timestamp=c.NOW,
            geometry=c.point_geometry(lat, lon),
            payload={
                "source_count": len(agents),
                "member_count": n,
                "sources": agents,
                "breakdown": dict(by_agent),
                "corroborated_by_satellite": has_nova,
            },
            related_ids=[s.id for s in members],
        ))

    # Strongest insights first
    out.sort(key=lambda s: s.confidence, reverse=True)
    return out
