import type { DetectionSet, EventItem, FeatureCollection } from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API ${path} → ${res.status}`);
  }
  return res.json() as Promise<T>;
}

/** All 136 signals (Nova as polygons + agents as points). */
export const fetchSignals = () => getJSON<FeatureCollection>("/signals");

/** Nova detections for a given set (full | inland | recent). */
export const fetchDetections = (set: DetectionSet = "full") =>
  getJSON<FeatureCollection>(`/detections?set=${set}`);

/** Existing building footprints for the AOI — the "all buildings" base layer. */
export const fetchFootprints = (aoi = "karrada") =>
  getJSON<FeatureCollection>(`/footprints?aoi=${aoi}`);

export const fetchEvents = (limit = 50) =>
  getJSON<{ count: number; events: EventItem[] }>(`/events?limit=${limit}`);

/** Trigger a (stubbed) Nova run; returns the new event. */
export async function triggerNovaRun(): Promise<EventItem> {
  const res = await fetch(`${API_BASE}/nova/run`, { method: "POST" });
  if (!res.ok) throw new Error(`POST /nova/run → ${res.status}`);
  const data = (await res.json()) as { event: EventItem };
  return data.event;
}
