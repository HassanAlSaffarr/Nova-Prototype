"""
Roberto — Survey Intelligence.

Generates ground-survey signals: residential rents, property asking prices,
retail footfall counts, and small-business confidence readings across Karrada.
Some land near Nova's detected change sites (a survey crew following up on new
construction); the rest are scattered.
"""

from nova.signals import AGENT_LAYER, Signal
from nova.agents import _common as c


def _anchor_map(nova_signals: list[Signal]) -> dict[str, str]:
    return {f"{s.lat:.6f},{s.lon:.6f}": s.id for s in nova_signals}


def _build(nova_signals: list[Signal], anchors, nmap, signal_type, en, ar,
           summary, value, unit, conf) -> Signal:
    lat, lon, key = c.sample_location(anchors)
    related = [nmap[key]] if key and key in nmap else []
    return Signal(
        id=c.new_id("roberto"),
        source_agent="roberto",
        layer=AGENT_LAYER["roberto"],
        signal_type=signal_type,
        lat=lat, lon=lon,
        title_en=en, title_ar=ar,
        summary=summary,
        value=value, unit=unit,
        confidence=conf,
        timestamp=c.recent_timestamp(),
        geometry=c.point_geometry(lat, lon),
        payload={"surveyor": c.person()[0]},
        related_ids=related,
    )


def generate(nova_signals: list[Signal], n: int = 22) -> list[Signal]:
    anchors = [(s.lat, s.lon) for s in nova_signals]
    nmap = _anchor_map(nova_signals)
    out: list[Signal] = []

    for _ in range(n):
        kind = c.pick(["rent", "price", "footfall", "confidence"])
        nb_en, nb_ar = c.pick(c.NEIGHBORHOODS)
        st_en, st_ar = c.pick(c.STREETS)

        if kind == "rent":
            v = float(c.randint(8, 26) * 50_000)  # IQD/month
            out.append(_build(
                nova_signals, anchors, nmap, "residential_rent",
                f"Residential rent survey — {nb_en}",
                f"مسح إيجارات سكنية — {nb_ar}",
                f"Median monthly rent for a 2-bedroom apartment in {nb_en} "
                f"surveyed at {v:,.0f} IQD.",
                v, "IQD/month", round(c.uniform(0.70, 0.92), 2),
            ))
        elif kind == "price":
            v = float(c.randint(80, 340) * 1_000)  # USD asking
            out.append(_build(
                nova_signals, anchors, nmap, "property_price",
                f"Property asking price — {nb_en}",
                f"سعر عقار معروض — {nb_ar}",
                f"Asking price for a residential unit in {nb_en} recorded at "
                f"${v:,.0f}.",
                v, "USD", round(c.uniform(0.65, 0.90), 2),
            ))
        elif kind == "footfall":
            v = float(c.randint(4, 50) * 50)  # daily pedestrians
            out.append(_build(
                nova_signals, anchors, nmap, "retail_footfall",
                f"Retail footfall — {st_en}",
                f"كثافة المتسوقين — {st_ar}",
                f"Estimated daily pedestrian footfall on {st_en} counted at "
                f"{v:,.0f} during survey hours.",
                v, "people/day", round(c.uniform(0.60, 0.85), 2),
            ))
        else:
            v = float(c.randint(35, 82))  # confidence index
            out.append(_build(
                nova_signals, anchors, nmap, "business_confidence",
                f"Business confidence index — {nb_en}",
                f"مؤشر ثقة الأعمال — {nb_ar}",
                f"Small-business confidence in {nb_en} surveyed at {v:.0f}/100 "
                f"this period.",
                v, "/100", round(c.uniform(0.70, 0.90), 2),
            ))

    return out
