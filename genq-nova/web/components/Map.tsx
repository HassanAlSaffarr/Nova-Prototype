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
import { KARRADA_BBOX, KARRADA_CENTER } from "@/lib/aoi";
import type { Feature, FeatureCollection, SourceAgent } from "@/lib/types";

const CARTO_DARK =
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const IRAQ_VIEW = { longitude: 43.7, latitude: 33.2, zoom: 5.2, pitch: 0 };

// Cinematic easing for the Iraq ↔ Karrada transition (easeInOutCubic).
const easeInOutCubic = (t: number) =>
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

const ACCENT = hexToRgb(AGENT_COLOR.nova);

function DeckOverlay(props: MapboxOverlayProps) {
  const overlay = useControl(() => new MapboxOverlay(props));
  overlay.setProps(props);
  return null;
}

function karradaOutline(): FeatureCollection {
  const [w, s, e, n] = KARRADA_BBOX;
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
  const activeAgents = useStore((s) => s.activeAgents);
  const selectedId = useStore((s) => s.selectedId);
  const select = useStore((s) => s.select);
  const setFlyToFn = useStore((s) => s.setFlyToFn);
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

  const flyTo = (target: "karrada" | "iraq") => {
    const map = mapRef.current;
    if (!map) return;
    if (target === "karrada") {
      map.flyTo({
        center: KARRADA_CENTER,
        zoom: 14.2,
        duration: 3000,
        curve: 1.6,
        easing: easeInOutCubic,
        essential: true,
      });
      setZoomed(true);
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
    // Halo beneath the detections — a wide, soft green stroke approximating an
    // outer glow so Nova reads as primary. The selected polygon's halo pulses.
    novaActive &&
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
        attributionControl={{ compact: true }}
        onClick={() => {
          // Empty-map click (not a feature) closes the panel.
          if (Date.now() - featureClickRef.current > 150) select(null);
        }}
        onMove={(e) => setDenseFill(e.viewState.zoom > 15)}
      >
        {/* Karrada AOI: subtle dashed marker of place; fades out past zoom 13 */}
        <Source id="karrada-aoi" type="geojson" data={karradaOutline()}>
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
        onClick={() => flyTo(zoomed ? "iraq" : "karrada")}
        className="absolute bottom-5 right-5 z-20 rounded-md border border-border bg-surface/90 px-4 py-2 text-sm font-semibold text-accent hover:bg-surface-2 transition-colors"
      >
        {zoomed ? "← Back to Iraq" : "Zoom to Karrada →"}
      </button>
    </div>
  );
}
