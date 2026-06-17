"""
Shared helpers and realistic Karrada content for the synthetic agents.

Everything routes through a single seeded RNG so the whole synthetic dataset is
reproducible run-to-run. Place names, streets, and people are bilingual
(English + Arabic) and plausible for central Baghdad.
"""

import math
import random
import uuid
from datetime import datetime, timedelta, timezone

from nova.config import KARRADA_BBOX

SEED = 20240620
_rng = random.Random(SEED)

# Demo "now": the pipeline pretends to run mid-June 2026
NOW = datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc)

_M_PER_DEG_LAT = 111_000.0
_M_PER_DEG_LON = 111_000.0 * math.cos(math.radians(33.3))


# ---------------------------------------------------------------------------
# Content banks (en, ar)
# ---------------------------------------------------------------------------

NEIGHBORHOODS = [
    ("Karrada Dakhil", "الكرادة داخل"),
    ("Karrada Kharij", "الكرادة خارج"),
    ("Arasat al-Hindiya", "عرصات الهندية"),
    ("Kahramana", "كهرمانة"),
    ("Jadriya", "الجادرية"),
    ("Masbah", "المسبح"),
    ("Babil", "بابل"),
    ("Al-Wahda", "الوحدة"),
    ("Karrada Maryam", "كرادة مريم"),
]

STREETS = [
    ("Arasat Street", "شارع عرصات"),
    ("52nd Street", "شارع ٥٢"),
    ("Al-Sadoun Street", "شارع السعدون"),
    ("Abu Nuwas Street", "شارع أبو نواس"),
    ("Karrada In Street", "شارع كرادة داخل"),
    ("Al-Nidhal Street", "شارع النضال"),
]

BUSINESS_TYPES = [
    ("restaurant", "مطعم"),
    ("electronics shop", "محل إلكترونيات"),
    ("money exchange", "مكتب صرافة"),
    ("real estate office", "مكتب عقاري"),
    ("café", "مقهى"),
    ("pharmacy", "صيدلية"),
    ("supermarket", "سوبر ماركت"),
    ("clothing store", "محل ملابس"),
    ("medical clinic", "عيادة طبية"),
    ("car showroom", "معرض سيارات"),
]

_FIRST_NAMES = [
    ("Ahmed", "أحمد"), ("Mustafa", "مصطفى"), ("Ali", "علي"), ("Hassan", "حسن"),
    ("Omar", "عمر"), ("Haider", "حيدر"), ("Sajjad", "سجاد"), ("Zainab", "زينب"),
    ("Fatima", "فاطمة"), ("Noor", "نور"), ("Sara", "سارة"), ("Maryam", "مريم"),
]
_SURNAMES = [
    ("al-Karkhi", "الكرخي"), ("al-Baghdadi", "البغدادي"), ("al-Obeidi", "العبيدي"),
    ("al-Janabi", "الجنابي"), ("al-Dulaimi", "الدليمي"), ("al-Tamimi", "التميمي"),
    ("al-Saadi", "الساعدي"),
]


# ---------------------------------------------------------------------------
# RNG helpers (all deterministic via the shared seed)
# ---------------------------------------------------------------------------


def pick(seq):
    return _rng.choice(seq)


def chance(p: float) -> bool:
    return _rng.random() < p


def randint(a: int, b: int) -> int:
    return _rng.randint(a, b)


def uniform(a: float, b: float) -> float:
    return _rng.uniform(a, b)


def new_id(agent: str) -> str:
    return f"{agent}-{uuid.UUID(int=_rng.getrandbits(128))}"


def recent_timestamp(max_days_ago: int = 21) -> datetime:
    """A random timestamp within the last few weeks of the demo 'now'."""
    delta = timedelta(
        days=_rng.randint(0, max_days_ago),
        hours=_rng.randint(0, 23),
        minutes=_rng.randint(0, 59),
    )
    return NOW - delta


def person() -> tuple[str, str]:
    fn_en, fn_ar = pick(_FIRST_NAMES)
    sn_en, sn_ar = pick(_SURNAMES)
    return f"{fn_en} {sn_en}", f"{fn_ar} {sn_ar}"


# ---------------------------------------------------------------------------
# Geo helpers
# ---------------------------------------------------------------------------


def random_point() -> tuple[float, float]:
    """Uniform random (lat, lon) inside the Karrada bbox."""
    w, s, e, n = KARRADA_BBOX
    return _rng.uniform(s, n), _rng.uniform(w, e)


def jitter(lat: float, lon: float, meters: float) -> tuple[float, float]:
    """Offset a point by up to `meters` in a random direction."""
    r = meters * math.sqrt(_rng.random())
    theta = _rng.uniform(0, 2 * math.pi)
    dlat = (r * math.sin(theta)) / _M_PER_DEG_LAT
    dlon = (r * math.cos(theta)) / _M_PER_DEG_LON
    return lat + dlat, lon + dlon


def point_geometry(lat: float, lon: float) -> dict:
    return {"type": "Point", "coordinates": [lon, lat]}


def meters_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Planar metric distance — accurate enough at Karrada's scale."""
    dy = (lat1 - lat2) * _M_PER_DEG_LAT
    dx = (lon1 - lon2) * _M_PER_DEG_LON
    return math.hypot(dx, dy)


def coarse_area(lat: float, lon: float) -> tuple[str, str]:
    """Rough N/central/S + E/W label for a point in the Karrada bbox."""
    w, s, e, n = KARRADA_BBOX
    ns = ("northern", "شمال") if lat > n - (n - s) / 3 else \
         ("southern", "جنوب") if lat < s + (n - s) / 3 else ("central", "وسط")
    ew = ("eastern", "شرق") if lon > e - (e - w) / 3 else \
         ("western", "غرب") if lon < w + (e - w) / 3 else ("", "")
    en = f"{ns[0]} Karrada" if not ew[0] else f"{ns[0]}-{ew[0]} Karrada"
    ar = f"{ns[1]} الكرادة" if not ew[1] else f"{ns[1]}-{ew[1]} الكرادة"
    return en, ar


def sample_location(
    anchors: list[tuple[float, float]],
    anchor_prob: float = 0.40,
    anchor_radius_m: float = 120.0,
) -> tuple[float, float, str | None]:
    """
    Pick a location. With probability `anchor_prob`, snap near one of the
    provided anchor points (Nova detection centroids) and return its index-key;
    otherwise return a scattered point with anchor=None.

    Returns (lat, lon, anchor_key) where anchor_key is the chosen anchor's
    "lat,lon" string (so the caller can record related_ids), or None.
    """
    if anchors and _rng.random() < anchor_prob:
        a_lat, a_lon = pick(anchors)
        lat, lon = jitter(a_lat, a_lon, anchor_radius_m)
        return lat, lon, f"{a_lat:.6f},{a_lon:.6f}"
    lat, lon = random_point()
    return lat, lon, None
