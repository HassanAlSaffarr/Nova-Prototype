"""
Namroud — Institutional Data.

Generates official / financial records: municipal building permits, government
tenders, new commercial registrations, and investment licenses. Permits in
particular are biased to land near Nova's detected construction (an official
record corroborating the satellite signal).
"""

from nova.signals import AGENT_LAYER, Signal
from nova.agents import _common as c


def _anchor_map(nova_signals: list[Signal]) -> dict[str, str]:
    return {f"{s.lat:.6f},{s.lon:.6f}": s.id for s in nova_signals}


def _signal(nova_signals, anchors, nmap, *, signal_type, en, ar, summary,
            value, unit, conf, payload, anchor_prob=0.40) -> Signal:
    lat, lon, key = c.sample_location(anchors, anchor_prob=anchor_prob)
    related = [nmap[key]] if key and key in nmap else []
    return Signal(
        id=c.new_id("namroud"),
        source_agent="namroud",
        layer=AGENT_LAYER["namroud"],
        signal_type=signal_type,
        lat=lat, lon=lon,
        title_en=en, title_ar=ar,
        summary=summary,
        value=value, unit=unit,
        confidence=conf,
        timestamp=c.recent_timestamp(40),
        geometry=c.point_geometry(lat, lon),
        payload=payload,
        related_ids=related,
    )


def generate(nova_signals: list[Signal], n: int = 18) -> list[Signal]:
    anchors = [(s.lat, s.lon) for s in nova_signals]
    nmap = _anchor_map(nova_signals)
    out: list[Signal] = []

    for _ in range(n):
        kind = c.pick(["permit", "permit", "tender", "registration", "investment"])
        nb_en, nb_ar = c.pick(c.NEIGHBORHOODS)
        st_en, st_ar = c.pick(c.STREETS)

        if kind == "permit":
            floors = c.randint(3, 16)
            use_en, use_ar = c.pick(
                [("residential", "سكني"), ("commercial", "تجاري"),
                 ("mixed-use", "متعدد الاستخدام")]
            )
            out.append(_signal(
                nova_signals, anchors, nmap,
                signal_type="building_permit",
                en=f"Building permit — {floors}-storey {use_en}, {nb_en}",
                ar=f"إجازة بناء — {use_ar} {floors} طوابق، {nb_ar}",
                summary=(
                    f"Amanat Baghdad issued a permit for a {floors}-storey "
                    f"{use_en} building in {nb_en}."
                ),
                value=float(floors), unit="storeys",
                conf=round(c.uniform(0.85, 0.98), 2),
                payload={"use": use_en, "permit_authority": "Amanat Baghdad"},
                anchor_prob=0.65,  # permits track real construction
            ))
        elif kind == "tender":
            v = float(c.randint(2, 40) * 50_000_000)  # IQD
            work_en, work_ar = c.pick(
                [("road resurfacing", "إعادة تبليط الطرق"),
                 ("drainage upgrade", "تأهيل المجاري"),
                 ("street lighting", "إنارة الشوارع"),
                 ("sidewalk rehabilitation", "تأهيل الأرصفة")]
            )
            out.append(_signal(
                nova_signals, anchors, nmap,
                signal_type="government_tender",
                en=f"Government tender — {work_en}, {st_en}",
                ar=f"مناقصة حكومية — {work_ar}، {st_ar}",
                summary=(
                    f"Public tender opened for {work_en} on {st_en}, "
                    f"budgeted at {v:,.0f} IQD."
                ),
                value=v, unit="IQD",
                conf=round(c.uniform(0.80, 0.95), 2),
                payload={"work_type": work_en, "status": "open"},
            ))
        elif kind == "registration":
            bt_en, bt_ar = c.pick(c.BUSINESS_TYPES)
            v = float(c.randint(10, 200) * 1_000_000)  # IQD capital
            owner_en, owner_ar = c.person()
            out.append(_signal(
                nova_signals, anchors, nmap,
                signal_type="commercial_registration",
                en=f"New commercial registration — {bt_en}, {nb_en}",
                ar=f"تسجيل تجاري جديد — {bt_ar}، {nb_ar}",
                summary=(
                    f"{owner_en} registered a new {bt_en} in {nb_en} with "
                    f"declared capital of {v:,.0f} IQD."
                ),
                value=v, unit="IQD",
                conf=round(c.uniform(0.82, 0.96), 2),
                payload={"business_type": bt_en, "owner": owner_en},
            ))
        else:
            v = float(c.randint(2, 60) * 250_000)  # USD
            out.append(_signal(
                nova_signals, anchors, nmap,
                signal_type="investment_license",
                en=f"Investment license — mixed-use project, {nb_en}",
                ar=f"إجازة استثمار — مشروع متعدد الاستخدام، {nb_ar}",
                summary=(
                    f"National Investment Commission granted a license for a "
                    f"mixed-use project in {nb_en} valued at ${v:,.0f}."
                ),
                value=v, unit="USD",
                conf=round(c.uniform(0.80, 0.95), 2),
                payload={"authority": "National Investment Commission"},
                anchor_prob=0.55,
            ))

    return out
