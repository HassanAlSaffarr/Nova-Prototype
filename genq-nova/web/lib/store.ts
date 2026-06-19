import { create } from "zustand";
import {
  fetchDetections,
  fetchEvents,
  fetchFootprints,
  fetchSignals,
  triggerNovaRun,
} from "./api";
import { AGENTS } from "./colors";
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

  detectionSet: DetectionSet;
  activeAgents: Record<SourceAgent, boolean>;
  showBuildings: boolean; // base "all buildings" layer toggle
  selectedId: string | null;
  eventLogOpen: boolean;
  runningNova: boolean;
  newEventId: string | null; // for the flash animation

  // Map registers a fly-to fn so the panel can pan to related signals.
  flyToFn: ((lon: number, lat: number) => void) | null;

  loadAll: () => Promise<void>;
  setDetectionSet: (s: DetectionSet) => Promise<void>;
  toggleAgent: (a: SourceAgent) => void;
  setAllAgents: (on: boolean) => void;
  toggleBuildings: () => void;
  select: (id: string | null) => void;
  selectRelated: (id: string) => void;
  setFlyToFn: (fn: (lon: number, lat: number) => void) => void;
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
function detectionToFeature(f: Feature): Feature {
  const p = f.properties;
  const confirmed = p.signal_type === "confirmed_change" ||
    (p as Record<string, unknown>).detection_type === "confirmed_change";
  const dndbi = (p as Record<string, unknown>).delta_ndbi;
  const dndvi = (p as Record<string, unknown>).delta_ndvi;
  return {
    ...f,
    properties: {
      ...p,
      source_agent: "nova",
      layer: "Geo-mapping",
      signal_type:
        (p.signal_type as string) ??
        ((p as Record<string, unknown>).detection_type as string),
      title_en: confirmed
        ? "Confirmed change detected"
        : "Candidate change detected",
      title_ar: confirmed ? "رصد تغيّر مؤكَّد" : "رصد تغيّر محتمل",
      summary: `Satellite change detection flagged a ${Number(
        p.area_m2,
      ).toLocaleString()} m² site (ΔNDBI ${dndbi}, ΔNDVI ${dndvi}).`,
      value: Number(p.area_m2),
      unit: "m²",
      timestamp:
        ((p as Record<string, unknown>).detected_at as string) ??
        p.timestamp,
      related_ids: (p.related_ids as string[]) ?? [],
    } as Feature["properties"],
  };
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
  detectionSet: "full",
  activeAgents: allOn(),
  showBuildings: true,
  selectedId: null,
  eventLogOpen: true,
  runningNova: false,
  newEventId: null,
  flyToFn: null,

  loadAll: async () => {
    set({ loading: true, error: null });
    try {
      const [signals, detections, events] = await Promise.all([
        fetchSignals(),
        fetchDetections(get().detectionSet),
        fetchEvents(),
      ]);
      const points = signals.features.filter(
        (f) => f.properties.source_agent !== "nova",
      );
      set({
        detections: detections.features,
        points,
        events: events.events,
        byId: indexById(detections.features, points),
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

  setDetectionSet: async (s) => {
    set({ detectionSet: s, selectedId: null });
    try {
      const detections = await fetchDetections(s);
      set({
        detections: detections.features,
        byId: indexById(detections.features, get().points),
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
