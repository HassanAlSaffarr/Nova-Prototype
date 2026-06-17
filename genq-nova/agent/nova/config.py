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

# Named AOI presets (CLI and future multi-city support)
AOI_PRESETS: dict[str, list[float]] = {
    "karrada": KARRADA_BBOX,
}

# UTM zone 38N — accurate metric CRS for Iraq (areas, distances, intersections)
CRS_UTM = "EPSG:32638"

# Repo data directory: genq-nova/agent/data
DATA_DIR = Path(__file__).parent.parent / "data"
