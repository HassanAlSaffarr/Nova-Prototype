"""
Sentinel-1 SAR change detection — the structure-aware core of Nova v2.

Optical indices (NDVI/NDBI) confuse new buildings with bare soil and exposed
riverbank, which dominated Nova v1's false positives in arid Karrada. SAR
backscatter responds to *structure* (buildings produce strong double-bounce),
so a backscatter increase is a far more specific signal for new construction.

This module builds a speckle-reduced VV/VH backscatter-change image (in dB) for
two date windows. Processing follows standard practice:
  1. filter to one orbit pass (Karrada is ASCENDING-only) for consistent geometry
  2. median composite in the power domain (not dB) to reduce speckle
  3. light spatial focal filter for residual speckle
  4. per-band log-ratio change:  ΔdB = 10·log10(after / before)

Positive ΔVV/ΔVH ⇒ more structure (candidate construction).
Assumes ee.Initialize() was called by the caller.
"""

import ee

from nova.config import CRS_UTM


def _s1_collection(
    aoi: ee.Geometry, start: str, end: str, orbit: str
) -> ee.ImageCollection:
    return (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(aoi)
        .filterDate(start, end)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .filter(ee.Filter.eq("orbitProperties_pass", orbit))
        .select(["VV", "VH"])
    )


def _db_to_power(img: ee.Image) -> ee.Image:
    return ee.Image(10.0).pow(img.divide(10.0))


def _power_to_db(img: ee.Image) -> ee.Image:
    return img.log10().multiply(10.0)


def sar_change(
    aoi_bounds: list[float],
    date_before: tuple[str, str],
    date_after: tuple[str, str],
    orbit: str = "ASCENDING",
    focal_m: float = 30.0,
) -> ee.Image:
    """Return a 2-band image (dVV, dVH) of speckle-reduced backscatter change
    in dB between the two windows. Positive ⇒ more structure."""
    aoi = ee.Geometry.Rectangle(aoi_bounds)

    def composite(coll: ee.ImageCollection) -> ee.Image:
        # Median in power domain reduces speckle; focal mean smooths residue.
        p = coll.map(_db_to_power).median()
        return p.focal_mean(radius=focal_m, units="meters")

    before = composite(_s1_collection(aoi, *date_before, orbit))
    after = composite(_s1_collection(aoi, *date_after, orbit))

    d_vv = _power_to_db(after.select("VV").divide(before.select("VV"))).rename("dVV")
    d_vh = _power_to_db(after.select("VH").divide(before.select("VH"))).rename("dVH")
    return d_vv.addBands(d_vh)


def scene_counts(
    aoi_bounds: list[float],
    date_before: tuple[str, str],
    date_after: tuple[str, str],
    orbit: str = "ASCENDING",
) -> tuple[int, int]:
    """(before, after) Sentinel-1 scene counts — for sanity logging."""
    aoi = ee.Geometry.Rectangle(aoi_bounds)
    b = _s1_collection(aoi, *date_before, orbit).size().getInfo()
    a = _s1_collection(aoi, *date_after, orbit).size().getInfo()
    return b, a
