export type SourceAgent =
  | "nova"
  | "roberto"
  | "namroud"
  | "peter"
  | "data_chef";

export type DetectionSet = "full" | "inland" | "recent";

export interface SignalProps {
  id: string;
  source_agent: SourceAgent;
  layer: string;
  signal_type: string;
  title_en: string;
  title_ar: string;
  summary: string;
  value: number | null;
  unit: string | null;
  confidence: number;
  timestamp: string;
  related_ids: string[];
  // Nova / agent extras land here too (delta_ndbi, sentiment, etc.)
  [key: string]: unknown;
}

export type Geometry =
  | { type: "Point"; coordinates: [number, number] }
  | { type: "Polygon"; coordinates: number[][][] }
  | { type: "MultiPolygon"; coordinates: number[][][][] };

export interface Feature {
  type: "Feature";
  geometry: Geometry;
  properties: SignalProps;
}

export interface FeatureCollection {
  type: "FeatureCollection";
  features: Feature[];
}

export interface EventItem {
  id: string;
  agent: string;
  event_type: string;
  timestamp: string;
  aoi: string;
  message: string;
  status: string;
  payload: Record<string, unknown>;
}
