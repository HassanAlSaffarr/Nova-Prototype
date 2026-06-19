"""
Esri World Imagery tile fetching — high-resolution visual confirmation.

Shared by nova.visualize (sample crops) and the API (/thumbnail). Esri is a
display/confirmation backdrop only, NOT a detection source (no SWIR/NIR, no
defined acquisition dates). Crops are centred exactly on the given lat/lon, so a
detection's thumbnail always shows the real changed spot.
"""

import io
import math

import httpx
from PIL import Image

ESRI_ZOOM = 18
ESRI_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)


def _deg2tile(lat: float, lon: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (
        1
        - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat)))
        / math.pi
    ) / 2 * n
    return x, y


def esri_crop(
    lat: float,
    lon: float,
    half_m: float = 160.0,
    size: int = 256,
    zoom: int = ESRI_ZOOM,
) -> Image.Image | None:
    """Fetch + stitch Esri World Imagery around (lat, lon), crop to the window
    and resize to `size`x`size`. Returns None if tiles can't be fetched."""
    dlat = half_m / 111_000.0
    dlon = half_m / (111_000.0 * math.cos(math.radians(lat)))
    north, south = lat + dlat, lat - dlat
    west, east = lon - dlon, lon + dlon

    x0f, y0f = _deg2tile(north, west, zoom)   # top-left
    x1f, y1f = _deg2tile(south, east, zoom)   # bottom-right
    x0, y0, x1, y1 = int(x0f), int(y0f), int(x1f), int(y1f)

    cols, rows = (x1 - x0 + 1), (y1 - y0 + 1)
    mosaic = Image.new("RGB", (cols * 256, rows * 256))
    try:
        with httpx.Client(timeout=20) as client:
            for ty in range(y0, y1 + 1):
                for tx in range(x0, x1 + 1):
                    resp = client.get(ESRI_URL.format(z=zoom, x=tx, y=ty))
                    resp.raise_for_status()
                    tile = Image.open(io.BytesIO(resp.content)).convert("RGB")
                    mosaic.paste(tile, ((tx - x0) * 256, (ty - y0) * 256))
    except (httpx.HTTPError, OSError):
        return None

    left = int((x0f - x0) * 256)
    top = int((y0f - y0) * 256)
    right = int((x1f - x0) * 256)
    bottom = int((y1f - y0) * 256)
    return mosaic.crop((left, top, right, bottom)).resize((size, size), Image.LANCZOS)
