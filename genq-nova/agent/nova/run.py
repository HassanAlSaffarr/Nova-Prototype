"""
Nova CLI — end-to-end change detection pipeline.

Usage:
    python -m nova.run \\
        --aoi karrada \\
        --before 2022-06-01:2022-09-01 \\
        --after  2024-06-01:2024-09-01

    nova-run --aoi karrada --before 2022-06-01:2022-09-01 --after 2024-06-01:2024-09-01

Requires:
    GEE_PROJECT env var set to your Google Cloud project ID.
    Karrada footprints downloaded (run `python -m nova.footprints` first).
"""

import argparse
import json
import os
import sys

import ee

from nova.change_detection import diff_raster_path
from nova.config import AOI_PRESETS, DATA_DIR
from nova.detections import filter_riverbank, run_nova


def _parse_date_range(value: str) -> tuple[str, str]:
    """Parse '2022-06-01:2022-09-01' → ('2022-06-01', '2022-09-01')."""
    parts = value.split(":")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(
            f"Expected YYYY-MM-DD:YYYY-MM-DD, got: {value!r}"
        )
    return (parts[0].strip(), parts[1].strip())


def _build_geojson(detections) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": d.geometry,
                "properties": {
                    "id": d.id,
                    "detection_type": d.detection_type,
                    "confidence": d.confidence,
                    "area_m2": d.area_m2,
                    "lat": d.lat,
                    "lon": d.lon,
                    "detected_at": d.detected_at.isoformat(),
                    **d.metadata,
                },
            }
            for d in detections
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Nova change detection pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--aoi",
        default="karrada",
        choices=list(AOI_PRESETS),
        help="AOI preset name (default: karrada)",
    )
    parser.add_argument(
        "--before",
        type=_parse_date_range,
        default=("2022-06-01", "2022-09-01"),
        metavar="START:END",
        help="Reference date window (default: 2022-06-01:2022-09-01)",
    )
    parser.add_argument(
        "--after",
        type=_parse_date_range,
        default=("2024-06-01", "2024-09-01"),
        metavar="START:END",
        help="Comparison date window (default: 2024-06-01:2024-09-01)",
    )
    parser.add_argument(
        "--cloud-threshold",
        type=int,
        default=20,
        metavar="PCT",
        help="Max CLOUDY_PIXEL_PERCENTAGE per S2 scene (default: 20)",
    )
    parser.add_argument(
        "--exclude-riverbank",
        action="store_true",
        help="Drop detections within 30 m of the water-mask boundary and write "
             "an inland-only set (detections_<aoi>_inland.geojson)",
    )
    args = parser.parse_args()

    project = os.environ.get("GEE_PROJECT")
    if not project:
        sys.exit(
            "GEE_PROJECT is not set.\n"
            "  export GEE_PROJECT=your-cloud-project-id"
        )

    print(f"Initialising Earth Engine (project={project})...")
    ee.Initialize(project=project)

    aoi_bounds = AOI_PRESETS[args.aoi]
    print(f"\n{'='*55}")
    print(f"  Nova — {args.aoi.upper()} change detection")
    print(f"  Before : {args.before[0]} → {args.before[1]}")
    print(f"  After  : {args.after[0]} → {args.after[1]}")
    print(f"  Cloud  : < {args.cloud_threshold}%")
    print(f"{'='*55}")

    detections = run_nova(
        aoi_bounds,
        args.before,
        args.after,
        cloud_threshold=args.cloud_threshold,
    )

    suffix = ""
    if args.exclude_riverbank:
        water_tif = diff_raster_path(args.before, args.after, args.cloud_threshold)
        before_n = len(detections)
        detections = filter_riverbank(detections, water_tif, buffer_m=30)
        suffix = "_inland"
        print(
            f"\n  Riverbank filter: {before_n} → {len(detections)} "
            f"({before_n - len(detections)} within 30 m of water excluded)"
        )

    # -----------------------------------------------------------------------
    # Print summary stats
    # -----------------------------------------------------------------------
    print(f"\n{'='*55}")
    print(f"  RESULTS: {len(detections)} detection(s)")
    print(f"{'='*55}")

    if not detections:
        print(
            "\n  No detections produced.\n"
            "  Tips:\n"
            "    • Widen the date windows (longer period = more change)\n"
            "    • Run with --cloud-threshold 40\n"
            "    • Loosen thresholds in change_detection.py "
            "(_DEFAULT_NDVI_THRESH, _DEFAULT_NDBI_THRESH)\n"
        )
        return

    # By type
    by_type: dict[str, list[float]] = {}
    for d in detections:
        by_type.setdefault(d.detection_type, []).append(d.confidence)

    print("\n  By type:")
    for dtype, confs in sorted(by_type.items()):
        avg = sum(confs) / len(confs)
        print(f"    {dtype:<22}  {len(confs):>4}  (avg confidence: {avg:.3f})")

    # Top 5
    print("\n  Top 5 highest-confidence detections:")
    for rank, d in enumerate(detections[:5], 1):
        print(
            f"    {rank}. {d.detection_type:<22}  "
            f"conf={d.confidence:.3f}  "
            f"area={d.area_m2:>7.0f} m²  "
            f"({d.lat:.5f}, {d.lon:.5f})"
        )

    # -----------------------------------------------------------------------
    # Save GeoJSON
    # -----------------------------------------------------------------------
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DATA_DIR / f"detections_{args.aoi}{suffix}.geojson"
    output_path.write_text(json.dumps(_build_geojson(detections), indent=2))
    print(f"\n  Saved → {output_path.resolve()}")
    print("  Drop it into https://geojson.io to eyeball results.\n")


if __name__ == "__main__":
    main()
