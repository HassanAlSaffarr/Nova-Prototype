"""
Peter — Social Listening.

Generates templated social-media chatter (Arabic + English) about Karrada:
posts about new openings, construction noise, traffic, and prices, plus
trending-topic readings. Lower confidence than official sources — social signal
is noisy — but high volume and good for sentiment texture on the map.
"""

from nova.signals import AGENT_LAYER, Signal
from nova.agents import _common as c

# (template_en, template_ar, sentiment) — {place} filled at generation time
_POST_TEMPLATES = [
    ("New {biz} just opened in {place}, the area is really changing 👀",
     "افتتح {biz_ar} جديد في {place_ar}، المنطقة تتغير بسرعة 👀", 0.6),
    ("Construction everywhere in {place} these days, so much dust and noise",
     "إنشاءات في كل مكان في {place_ar} هاي الأيام، غبار وضجيج",  -0.4),
    ("Traffic on {street} is unbearable since the new building works started",
     "الزحام في {street_ar} لا يطاق من بدت أعمال البناء الجديدة", -0.6),
    ("Rents in {place} are getting crazy, landlords asking double now",
     "إيجارات {place_ar} صارت خيالية، أصحاب الملك يطلبون الضعف", -0.5),
    ("Love the new cafés popping up around {place}, great vibe lately",
     "أحب المقاهي الجديدة حول {place_ar}، الأجواء حلوة مؤخراً", 0.7),
    ("Heard a big new tower is coming to {place}, anyone know the developer?",
     "سمعت برج جديد كبير راح ينبني في {place_ar}، أحد يعرف المطور؟", 0.2),
]

_TRENDS = [
    ("#KarradaDevelopment", "#تطوير_الكرادة"),
    ("#BaghdadRealEstate", "#عقارات_بغداد"),
    ("#ArasatNights", "#ليالي_عرصات"),
    ("#KarradaTraffic", "#زحام_الكرادة"),
]


def _anchor_map(nova_signals: list[Signal]) -> dict[str, str]:
    return {f"{s.lat:.6f},{s.lon:.6f}": s.id for s in nova_signals}


def generate(nova_signals: list[Signal], n: int = 30) -> list[Signal]:
    anchors = [(s.lat, s.lon) for s in nova_signals]
    nmap = _anchor_map(nova_signals)
    out: list[Signal] = []

    for _ in range(n):
        if c.chance(0.18):
            # trending topic — area-level, scattered
            lat, lon = c.random_point()
            tag_en, tag_ar = c.pick(_TRENDS)
            mentions = float(c.randint(40, 1200))
            out.append(Signal(
                id=c.new_id("peter"),
                source_agent="peter",
                layer=AGENT_LAYER["peter"],
                signal_type="trending_topic",
                lat=lat, lon=lon,
                title_en=f"Trending — {tag_en}",
                title_ar=f"يتداول — {tag_ar}",
                summary=f"{tag_en} mentioned {mentions:,.0f} times across Karrada "
                        f"this week.",
                value=mentions, unit="mentions",
                confidence=round(c.uniform(0.45, 0.70), 2),
                timestamp=c.recent_timestamp(10),
                geometry=c.point_geometry(lat, lon),
                payload={"hashtag_en": tag_en, "hashtag_ar": tag_ar},
                related_ids=[],
            ))
            continue

        # individual post — biased toward Nova sites (chatter near real change)
        lat, lon, key = c.sample_location(anchors, anchor_prob=0.45)
        related = [nmap[key]] if key and key in nmap else []
        tmpl_en, tmpl_ar, sentiment = c.pick(_POST_TEMPLATES)
        nb_en, nb_ar = c.pick(c.NEIGHBORHOODS)
        st_en, st_ar = c.pick(c.STREETS)
        biz_en, biz_ar = c.pick(c.BUSINESS_TYPES)
        text_en = tmpl_en.format(biz=biz_en, place=nb_en, street=st_en)
        text_ar = tmpl_ar.format(biz_ar=biz_ar, place_ar=nb_ar, street_ar=st_ar)
        engagement = float(c.randint(3, 480))
        out.append(Signal(
            id=c.new_id("peter"),
            source_agent="peter",
            layer=AGENT_LAYER["peter"],
            signal_type="social_post",
            lat=lat, lon=lon,
            title_en=f"Social post — {nb_en}",
            title_ar=f"منشور اجتماعي — {nb_ar}",
            summary=text_en,
            value=round(sentiment, 2), unit="sentiment",
            confidence=round(c.uniform(0.45, 0.78), 2),
            timestamp=c.recent_timestamp(10),
            geometry=c.point_geometry(lat, lon),
            payload={
                "text_en": text_en,
                "text_ar": text_ar,
                "sentiment": sentiment,
                "engagement": engagement,
                "platform": c.pick(["X", "Facebook", "Instagram", "Telegram"]),
            },
            related_ids=related,
        ))

    return out
