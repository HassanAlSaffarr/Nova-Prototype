"""
Tier-3 verification — corroborate a detected construction site against the web.

A satellite detection says *something was built here*. This module turns the
coordinates into a searchable place and a query the (Namroud/Peter) agents or a
search API can run to look for matching project news, permits, or chatter.

IMPORTANT: verification is ONE-DIRECTIONAL. Finding online evidence raises
confidence that a detection is a real, known project. Finding nothing does NOT
mean the detection is false — many Iraqi projects have no online footprint, which
is precisely why Nova detects from imagery in the first place.
"""

import httpx

NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
_HEADERS = {"User-Agent": "nova-geo-intelligence/0.2 (genq prototype)"}


def reverse_geocode(lat: float, lon: float) -> dict:
    """Resolve a lat/lon to a place via OpenStreetMap Nominatim (free, keyless)."""
    r = httpx.get(
        NOMINATIM,
        params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 16,
                "addressdetails": 1},
        headers=_HEADERS,
        timeout=20,
        follow_redirects=True,
    )
    r.raise_for_status()
    d = r.json()
    addr = d.get("address", {})
    parts = [
        addr.get(k)
        for k in ("neighbourhood", "suburb", "quarter", "city_district",
                  "city", "town", "county", "state")
        if addr.get(k)
    ]
    return {
        "display_name": d.get("display_name", ""),
        "area": ", ".join(dict.fromkeys(parts)),   # de-duped, coarse→fine
        "address": addr,
    }


def verification_query(place: dict) -> str:
    """Build a web-search query to look for a real project at this place."""
    area = place.get("area") or place.get("display_name", "")
    return f'new construction OR development OR project "{area}" Iraq 2025 2026'


def verify_site(lat: float, lon: float) -> dict:
    """Reverse-geocode a detection and produce its verification query.
    The actual web search is run by an agent / search API with that query."""
    place = reverse_geocode(lat, lon)
    return {
        "lat": lat, "lon": lon,
        "area": place["area"],
        "display_name": place["display_name"],
        "query": verification_query(place),
    }
