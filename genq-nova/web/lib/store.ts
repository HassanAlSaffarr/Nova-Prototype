import { create } from "zustand";
import {
  fetchDetections,
  fetchEvents,
  fetchFootprints,
  fetchSignals,
  triggerNovaRun,
} from "./api";
import { AGENTS } from "./colors";
import { type AoiKey } from "./aoi";
import type {
  DetectionSet,
  EventItem,
  Feature,
  FeatureCollection,
  SourceAgent,
} from "./types";

interface NovaState {
  loading: boolean;
  error: string | null;

  detections: Feature[]; // Nova polygons for the active set
  points: Feature[]; // the 86 non-Nova agent signals
  buildings: FeatureCollection | null; // existing-building footprints base layer
  events: EventItem[];
  byId: Record<string, Feature>;

  aoi: AoiKey;
  detectionSet: DetectionSet;
  activeAgents: Record<SourceAgent, boolean>;
  showBuildings: boolean; // base "all buildings" layer toggle
  selectedId: string | null;
  eventLogOpen: boolean;
  runningNova: boolean;
  newEventId: string | null; // for the flash animation

  // Map registers a fly-to fn so the panel can pan to related signals,
  // and a fly-to-AOI fn so switching AOI reframes the map.
  flyToFn: ((lon: number, lat: number) => void) | null;
  flyToAoiFn: ((aoi: AoiKey) => void) | null;

  loadAll: () => Promise<void>;
  focusAoi: (aoi: AoiKey) => void;
  setDetectionSet: (s: DetectionSet) => Promise<void>;
  toggleAgent: (a: SourceAgent) => void;
  setAllAgents: (on: boolean) => void;
  toggleBuildings: () => void;
  select: (id: string | null) => void;
  selectRelated: (id: string) => void;
  setFlyToFn: (fn: (lon: number, lat: number) => void) => void;
  setFlyToAoiFn: (fn: (aoi: AoiKey) => void) => void;
  toggleEventLog: () => void;
  runNova: () => Promise<void>;
  clearError: () => void;
}

const allOn = () =>
  AGENTS.reduce(
    (acc, a) => ({ ...acc, [a]: true }),
    {} as Record<SourceAgent, boolean>,
  );

// Raw /detections features lack the Signal envelope (title/summary/etc).
// Normalise one into the same shape the panel expects for every agent.
// Two detector families flow through here: v1 (10m optical polygons, with
// delta_ndbi/ndvi) and v2 (high-res structural-change point sites, with
// mean_delta/n_cells). Branch on the v2 `method` marker.
function detectionToFeature(f: Feature): Feature {
  const p = f.properties as Record<string, unknown>;

  if (p.method === "highres") {
    const area = Number(p.area_m2);
    return {
      ...f,
      properties: {
        ...(p as Feature["properties"]),
        source_agent: "nova",
        layer: "Geo-mapping",
        signal_type: "confirmed_change",
        title_en: "New construction (high-res)",
        title_ar: "إنشاءات جديدة (دقة عالية)",
        summary: `High-resolution structural-change detection flagged a ${area.toLocaleString()} m² site where smooth, bare ground became built structure between ${String(
          p.before,
        )} and ${String(p.after)} (Δstructure ${String(p.mean_delta)}).`,
        value: area,
        unit: "m²",
        timestamp: (p.detected_at as string) ?? (p.timestamp as string),
        related_ids: (p.related_ids as string[]) ?? [],
      } as Feature["properties"],
    };
  }

  const confirmed =
    p.signal_type === "confirmed_change" ||
    p.detection_type === "confirmed_change";
  const dndbi = p.delta_ndbi;
  const dndvi = p.delta_ndvi;
  return {
    ...f,
    properties: {
      ...(p as Feature["properties"]),
      source_agent: "nova",
      layer: "Geo-mapping",
      signal_type: (p.signal_type as string) ?? (p.detection_type as string),
      title_en: confirmed
        ? "Confirmed change detected"
        : "Candidate change detected",
      title_ar: confirmed ? "رصد تغيّر مؤكَّد" : "رصد تغيّر محتمل",
      summary: `Satellite change detection flagged a ${Number(
        p.area_m2,
      ).toLocaleString()} m² site (ΔNDBI ${dndbi}, ΔNDVI ${dndvi}).`,
      value: Number(p.area_m2),
      unit: "m²",
      timestamp: (p.detected_at as string) ?? (p.timestamp as string),
      related_ids: (p.related_ids as string[]) ?? [],
    } as Feature["properties"],
  };
}

// Fetch the detections for a method. "highres" shows EVERY AOI at once — the
// product scales to all of Iraq, so the map isn't gated to one area at a time;
// the legacy v1 sets are Karrada-only.
async function loadDetectionsFor(set: DetectionSet): Promise<Feature[]> {
  if (set === "highres") {
    const [kar, bis] = await Promise.all([
      fetchDetections("highres"),
      fetchDetections("highres_bismayah"),
    ]);
    return [...kar.features, ...bis.features];
  }
  return (await fetchDetections(set)).features;
}

function indexById(detections: Feature[], points: Feature[]) {
  const byId: Record<string, Feature> = {};
  for (const f of points) byId[f.properties.id] = f;
  // Nova entries come from the (normalised) detection set, so the panel works
  // for full / inland / recent uniformly.
  for (const f of detections) byId[f.properties.id] = detectionToFeature(f);
  return byId;
}

export const useStore = create<NovaState>((set, get) => ({
  loading: true,
  error: null,
  detections: [],
  points: [],
  buildings: null,
  events: [],
  byId: {},
  aoi: "karrada",
  detectionSet: "highres", // demo opens on the validated v2 detector
  activeAgents: allOn(),
  showBuildings: true,
  selectedId: null,
  eventLogOpen: true,
  runningNova: false,
  newEventId: null,
  flyToFn: null,
  flyToAoiFn: null,

  loadAll: async () => {
    set({ loading: true, error: null });
    try {
      const [signals, detections, events] = await Promise.all([
        fetchSignals(),
        loadDetectionsFor(get().detectionSet),
        fetchEvents(),
      ]);
      const points = signals.features.filter(
        (f) => f.properties.source_agent !== "nova",
      );
      set({
        detections,
        points,
        events: events.events,
        byId: indexById(detections, points),
        loading: false,
      });
      // Buildings are a heavy, non-critical base layer — load them after the
      // core data so a slow/absent footprints file never blanks the demo.
      fetchFootprints()
        .then((fc) => set({ buildings: fc }))
        .catch(() => {});
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  // AOIs all render at once now; "focus" just flies the camera to one.
  focusAoi: (aoi) => {
    set({ aoi });
    get().flyToAoiFn?.(aoi);
  },

  setDetectionSet: async (s) => {
    set({ detectionSet: s, selectedId: null });
    try {
      const detections = await loadDetectionsFor(s);
      set({
        detections,
        byId: indexById(detections, get().points),
      });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  toggleAgent: (a) =>
    set((st) => ({
      activeAgents: { ...st.activeAgents, [a]: !st.activeAgents[a] },
    })),

  setAllAgents: (on) =>
    set({
      activeAgents: AGENTS.reduce(
        (acc, a) => ({ ...acc, [a]: on }),
        {} as Record<SourceAgent, boolean>,
      ),
    }),

  toggleBuildings: () => set((st) => ({ showBuildings: !st.showBuildings })),

  select: (id) => set({ selectedId: id }),

  selectRelated: (id) => {
    const f = get().byId[id];
    set({ selectedId: id });
    const fly = get().flyToFn;
    if (f && fly) fly(f.properties.lon, f.properties.lat);
  },

  setFlyToFn: (fn) => set({ flyToFn: fn }),

  setFlyToAoiFn: (fn) => set({ flyToAoiFn: fn }),

  toggleEventLog: () => set((st) => ({ eventLogOpen: !st.eventLogOpen })),

  clearError: () => set({ error: null }),

  runNova: async () => {
    set({ runningNova: true });
    try {
      const ev = await triggerNovaRun();
      set((st) => ({
        events: [ev, ...st.events],
        newEventId: ev.id,
        runningNova: false,
      }));
      setTimeout(() => set({ newEventId: null }), 2000);
    } catch (e) {
      set({ error: (e as Error).message, runningNova: false });
    }
  },
}));
