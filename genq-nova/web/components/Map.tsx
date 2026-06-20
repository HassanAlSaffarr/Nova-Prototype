"use client";

import { useEffect, useRef, useState } from "react";
import MapGL, {
  Layer,
  Source,
  useControl,
  type MapRef,
} from "react-map-gl/maplibre";
import { MapboxOverlay, type MapboxOverlayProps } from "@deck.gl/mapbox";
import { GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import "maplibre-gl/dist/maplibre-gl.css";

import { useStore } from "@/lib/store";
import { AGENT_COLOR, hexToRgb } from "@/lib/colors";
import { AOIS, KARRADA_CENTER, type AoiKey } from "@/lib/aoi";
import type { Feature, FeatureCollection, SourceAgent } from "@/lib/types";

const CARTO_DARK =
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const IRAQ_VIEW = { longitude: 43.7, latitude: 33.2, zoom: 5.2, pitch: 0 };

// Cinematic easing for the Iraq ↔ Karrada transition (easeInOutCubic).
const easeInOutCubic = (t: number) =>
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

const ACCENT = hexToRgb(AGENT_COLOR.nova);
// Land-emergence (river land exposed as water drops) reads in neutral slate —
// deliberately NOT an agent colour and not the brand green, so it's clearly
// "Nova flagged this, but it isn't construction".
const LAND_EMERGENCE: [number, number, number] = [156, 163, 175];

const siteColor = (f: Feature): [number, number, number] =>
  f.properties.category === "land_emergence" ? LAND_EMERGENCE : ACCENT;

function DeckOverlay(props: MapboxOverlayProps) {
  const overlay = useControl(() => new MapboxOverlay(props));
  overlay.setProps(props);
  return null;
}

function aoiOutline(bbox: [number, number, number, number]): FeatureCollection {
  const [w, s, e, n] = bbox;
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [w, s],
              [e, s],
              [e, n],
              [w, n],
              [w, s],
            ],
          ],
        },
        properties: {} as Feature["properties"],
      },
    ],
  };
}

export default function Map() {
  const mapRef = useRef<MapRef>(null);
  const [iraq, setIraq] = useState<FeatureCollection | null>(null);
  const [zoomed, setZoomed] = useState(false);
  const [pulse, setPulse] = useState(0); // 0..1, drives selection pulse
  const [denseFill, setDenseFill] = useState(false); // true past zoom 15

  const detections = useStore((s) => s.detections);
  const points = useStore((s) => s.points);
  const buildings = useStore((s) => s.buildings);
  const showBuildings = useStore((s) => s.showBuildings);
  const activeAgents = useStore((s) => s.activeAgents);
  const selectedId = useStore((s) => s.selectedId);
  const aoi = useStore((s) => s.aoi);
  const select = useStore((s) => s.select);
  const setFlyToFn = useStore((s) => s.setFlyToFn);
  const setFlyToAoiFn = useStore((s) => s.setFlyToAoiFn);
  const loadAll = useStore((s) => s.loadAll);

  // Guards against an empty-map click deselecting right after a feature click.
  const featureClickRef = useRef(0);

  useEffect(() => {
    loadAll();
    fetch("/iraq.geojson")
      .then((r) => r.json())
      .then(setIraq)
      .catch(() => {});
  }, [loadAll]);

  useEffect(() => {
    setFlyToFn((lon, lat) =>
      mapRef.current?.flyTo({
        center: [lon, lat],
        zoom: 15.5,
        duration: 1500,
        essential: true,
      }),
    );
  }, [setFlyToFn]);

  const handlePick = (info: { object?: Feature }) => {
    if (info.object) {
      featureClickRef.current = Date.now();
      select(info.object.properties.id);
    }
  };

  // Pulse only while a Nova polygon is selected (not always — too busy).
  const novaSelected =
    !!selectedId && detections.some((d) => d.properties.id === selectedId);
  useEffect(() => {
    if (!novaSelected) {
      setPulse(0);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const loop = (t: number) => {
      setPulse((Math.sin((t - start) / 320) + 1) / 2);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [novaSelected]);

  const flyToAoi = (key: AoiKey, duration = 3000) => {
    const def = AOIS[key];
    mapRef.current?.flyTo({
      center: def.center,
      zoom: def.zoom,
      duration,
      curve: 1.6,
      easing: easeInOutCubic,
      essential: true,
    });
    setZoomed(true);
  };

  // Switching AOI from the panel reframes the map.
  useEffect(() => {
    setFlyToAoiFn((key) => flyToAoi(key, 2200));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setFlyToAoiFn]);

  const flyTo = (target: "aoi" | "iraq") => {
    const map = mapRef.current;
    if (!map) return;
    if (target === "aoi") {
      flyToAoi(aoi);
    } else {
      map.flyTo({
        center: [IRAQ_VIEW.longitude, IRAQ_VIEW.latitude],
        zoom: IRAQ_VIEW.zoom,
        duration: 3000,
        curve: 1.6,
        easing: easeInOutCubic,
        essential: true,
      });
      setZoomed(false);
    }
  };

  const novaActive = activeAgents.nova;
  const visiblePoints = points.filter(
    (f) => activeAgents[f.properties.source_agent as SourceAgent],
  );

  // The v2 (high-res) detector emits site *points*; v1 emits change *polygons*.
  // Render each in its own idiom: polygons get the glow/fill treatment, points
  // get a distinct hollow target-ring so a Nova "change" never looks like an
  // agent's solid dot.
  const novaArePoints =
    detections.length > 0 && detections[0].geometry.type === "Point";

  const layers = [
    iraq &&
      new GeoJsonLayer({
        id: "iraq",
        data: iraq,
        stroked: true,
        filled: true,
        getFillColor: [20, 28, 48, 120],
        getLineColor: [80, 100, 140, 200],
        getLineWidth: 1,
        lineWidthMinPixels: 1,
      }),
    // Base "all buildings" layer: every existing Karrada footprint, a faint
    // blue-grey wash beneath everything (24k polygons — trivial for deck.gl, so
    // no zoom gate; they're sub-pixel specks when zoomed out anyway). This is the
    // stage between an empty basemap and Nova's flagged *changes*.
    showBuildings &&
      buildings &&
      new GeoJsonLayer({
        id: "buildings",
        data: buildings,
        stroked: true,
        filled: true,
        getFillColor: [90, 110, 150, 28],
        getLineColor: [120, 140, 180, 90],
        getLineWidth: 0.5,
        lineWidthMinPixels: 0.5,
        lineWidthMaxPixels: 1.5,
        pickable: false,
        parameters: { depthTest: false },
      }),
    // Halo beneath the detections — a wide, soft green stroke approximating an
    // outer glow so Nova reads as primary. The selected polygon's halo pulses.
    novaActive &&
      !novaArePoints &&
      new GeoJsonLayer({
        id: "nova-glow",
        data: { type: "FeatureCollection", features: detections },
        stroked: true,
        filled: false,
        getLineColor: (f: Feature) =>
          f.properties.id === selectedId
            ? ([...ACCENT, 60 + pulse * 120] as [number, number, number, number])
            : ([...ACCENT, 55] as [number, number, number, number]),
        getLineWidth: (f: Feature) =>
          f.properties.id === selectedId ? 9 + pulse * 9 : 6,
        lineWidthMinPixels: 4,
        lineWidthMaxPixels: 22,
        updateTriggers: {
          getLineColor: [selectedId, pulse],
          getLineWidth: [selectedId, pulse],
        },
      }),
    novaActive &&
      !novaArePoints &&
      new GeoJsonLayer({
        id: "nova-detections",
        data: { type: "FeatureCollection", features: detections },
        stroked: true,
        filled: true,
        getFillColor: (f: Feature) =>
          f.properties.id === selectedId
            ? [...ACCENT, 210]
            : [...ACCENT, denseFill ? 102 : 90], // denser past zoom 15
        getLineColor: [...ACCENT, 255] as [number, number, number, number],
        getLineWidth: 2,
        lineWidthMinPixels: 1.5,
        pickable: true,
        onClick: handlePick,
        updateTriggers: { getFillColor: [selectedId, denseFill] },
      }),
    // v2 high-res sites: a hollow target-ring, radius scaled by site area,
    // pulsing when selected. Deliberately unlike the agents' solid dots.
    // Construction → neon green (a real building change); land_emergence → sky
    // blue (riverbed land exposed as water dropped) so the two read apart.
    novaActive &&
      novaArePoints &&
      new ScatterplotLayer({
        id: "nova-sites",
        data: detections,
        getPosition: (f: Feature) =>
          (f.geometry as { coordinates: [number, number] }).coordinates,
        getRadius: (f: Feature) =>
          Math.sqrt(Number(f.properties.area_m2) || 0) / 2 + 12,
        radiusMinPixels: 9,
        radiusMaxPixels: 60,
        stroked: true,
        filled: true,
        getFillColor: (f: Feature) => {
          const c = siteColor(f);
          return [...c, f.properties.id === selectedId ? 70 : 28] as [
            number, number, number, number,
          ];
        },
        getLineColor: (f: Feature) => {
          const c = siteColor(f);
          return [...c, f.properties.id === selectedId ? 255 : 200] as [
            number, number, number, number,
          ];
        },
        getLineWidth: (f: Feature) =>
          f.properties.id === selectedId ? 3 + pulse * 3 : 2.5,
        lineWidthMinPixels: 2,
        lineWidthMaxPixels: 6,
        pickable: true,
        onClick: handlePick,
        updateTriggers: {
          getFillColor: [selectedId],
          getLineColor: [selectedId],
          getLineWidth: [selectedId, pulse],
        },
      }),
    new ScatterplotLayer({
      id: "agent-points",
      data: visiblePoints,
      getPosition: (f: Feature) =>
        (f.geometry as { coordinates: [number, number] }).coordinates,
      getFillColor: (f: Feature) =>
        hexToRgb(AGENT_COLOR[f.properties.source_agent as SourceAgent]),
      getRadius: (f: Feature) =>
        f.properties.id === selectedId ? 14 : 8,
      radiusMinPixels: 4,
      radiusMaxPixels: 16,
      stroked: true,
      getLineColor: [10, 14, 26, 255],
      lineWidthMinPixels: 1,
      pickable: true,
      onClick: handlePick,
      updateTriggers: { getRadius: [selectedId] },
    }),
  ].filter(Boolean);

  return (
    <div className="absolute inset-0">
      <MapGL
        ref={mapRef}
        initialViewState={IRAQ_VIEW}
        mapStyle={CARTO_DARK}
        style={{ width: "100%", height: "100%" }}
        attributionControl={false}
        onClick={() => {
          // Empty-map click (not a feature) closes the panel.
          if (Date.now() - featureClickRef.current > 150) select(null);
        }}
        onMove={(e) => setDenseFill(e.viewState.zoom > 15)}
      >
        {/* Karrada AOI: subtle dashed marker of place; fades out past zoom 13 */}
        <Source id="karrada-aoi" type="geojson" data={aoiOutline(AOIS[aoi].bbox)}>
          <Layer
            id="karrada-aoi-line"
            type="line"
            paint={{
              "line-color": "#00ff9d",
              "line-width": 1.5,
              "line-dasharray": [3, 3],
              "line-opacity": [
                "interpolate",
                ["linear"],
                ["zoom"],
                6,
                0.3,
                12.5,
                0.3,
                13,
                0,
              ],
            }}
          />
        </Source>
        <DeckOverlay layers={layers} />
      </MapGL>

      <button
        onClick={() => flyTo(zoomed ? "iraq" : "aoi")}
        className="absolute bottom-5 right-5 z-20 rounded-md border border-border bg-surface/90 px-4 py-2 text-sm font-semibold text-accent hover:bg-surface-2 transition-colors"
      >
        {zoomed ? "← Back to Iraq" : `Zoom to ${AOIS[aoi].label} →`}
      </button>

      {/* Minimal attribution — required by CARTO/OSM, expands on hover */}
      <div className="group absolute bottom-1 right-1 z-10">
        <div className="flex items-center gap-1 rounded-full border border-border bg-bg/70 px-1.5 py-0.5 text-[10px] text-muted backdrop-blur">
          <span className="flex h-3 w-3 items-center justify-center rounded-full border border-muted text-[8px] italic">
            i
          </span>
          <span className="hidden whitespace-nowrap group-hover:inline">
            © CARTO · © OpenStreetMap
          </span>
        </div>
      </div>
    </div>
  );
}
