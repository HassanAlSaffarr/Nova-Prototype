import { create } from "zustand";
import {
  fetchDetections,
  fetchEvents,
  fetchSignals,
  triggerNovaRun,
} from "./api";
import { AGENTS } from "./colors";
import type {
  DetectionSet,
  EventItem,
  Feature,
  SourceAgent,
} from "./types";

interface NovaState {
  loading: boolean;
  error: string | null;

  detections: Feature[]; // Nova polygons for the active set
  points: Feature[]; // the 86 non-Nova agent signals
  events: EventItem[];
  byId: Record<string, Feature>;

  detectionSet: DetectionSet;
  activeAgents: Record<SourceAgent, boolean>;
  selectedId: string | null;
  eventLogOpen: boolean;
  runningNova: boolean;
  newEventId: string | null; // for the flash animation

  loadAll: () => Promise<void>;
  setDetectionSet: (s: DetectionSet) => Promise<void>;
  toggleAgent: (a: SourceAgent) => void;
  select: (id: string | null) => void;
  toggleEventLog: () => void;
  runNova: () => Promise<void>;
}

const allOn = () =>
  AGENTS.reduce(
    (acc, a) => ({ ...acc, [a]: true }),
    {} as Record<SourceAgent, boolean>,
  );

function indexById(detections: Feature[], points: Feature[]) {
  const byId: Record<string, Feature> = {};
  // Nova polygons first so a Nova id resolves to its polygon, not its point twin
  for (const f of detections) byId[f.properties.id] = f;
  for (const f of points) byId[f.properties.id] = f;
  return byId;
}

export const useStore = create<NovaState>((set, get) => ({
  loading: true,
  error: null,
  detections: [],
  points: [],
  events: [],
  byId: {},
  detectionSet: "full",
  activeAgents: allOn(),
  selectedId: null,
  eventLogOpen: true,
  runningNova: false,
  newEventId: null,

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

  select: (id) => set({ selectedId: id }),

  toggleEventLog: () => set((st) => ({ eventLogOpen: !st.eventLogOpen })),

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
