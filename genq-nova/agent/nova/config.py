"""
Shared configuration constants for the Nova agent.

Single source of truth for the AOI, the metric CRS, and the data directory so
they aren't redefined (under three different names) across modules. Treat the
AOI as config: adding another city later means adding an entry here, not editing
four files.
"""

from pathlib import Path

# Karrada peninsula, central Baghdad  [west, south, east, north] in WGS84 degrees
KARRADA_BBOX = [44.385, 33.285, 44.430, 33.320]

# Bismayah New City, SE of Baghdad — a documented 100k-unit megaproject actively
# under construction; the high-change counterpart to built-out Karrada.
BISMAYAH_BBOX = [44.595, 33.175, 44.642, 33.213]

# Named AOI presets (CLI and multi-city support)
AOI_PRESETS: dict[str, list[float]] = {
    "karrada": KARRADA_BBOX,
    "bismayah": BISMAYAH_BBOX,
}

# UTM zone 38N — accurate metric CRS for Iraq (areas, distances, intersections)
CRS_UTM = "EPSG:32638"

# Repo data directory: genq-nova/agent/data
DATA_DIR = Path(__file__).parent.parent / "data"
