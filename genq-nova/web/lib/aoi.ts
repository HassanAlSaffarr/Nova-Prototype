import type { DetectionSet } from "./types";

export type AoiKey = "karrada" | "bismayah";

export interface AoiDef {
  key: AoiKey;
  label: string;
  sublabel: string;
  bbox: [number, number, number, number]; // [w, s, e, n]
  center: [number, number];
  zoom: number;
  detectionSet: DetectionSet; // which Nova set this AOI serves
  hasBuildings: boolean; // MS footprints base layer available?
  hasAgents: boolean; // synthetic agent signals anchored here?
}

const center = (
  b: [number, number, number, number],
): [number, number] => [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];

const KARRADA: [number, number, number, number] = [44.385, 33.285, 44.43, 33.32];
const BISMAYAH: [number, number, number, number] = [
  44.595, 33.175, 44.642, 33.213,
];

export const AOIS: Record<AoiKey, AoiDef> = {
  karrada: {
    key: "karrada",
    label: "Karrada",
    sublabel: "built-out core",
    bbox: KARRADA,
    center: center(KARRADA),
    zoom: 14.2,
    detectionSet: "highres",
    hasBuildings: true,
    hasAgents: true,
  },
  bismayah: {
    key: "bismayah",
    label: "Bismayah",
    sublabel: "new city · active build",
    bbox: BISMAYAH,
    center: center(BISMAYAH),
    zoom: 13.4,
    detectionSet: "highres_bismayah",
    hasBuildings: false,
    hasAgents: false,
  },
};

export const AOI_KEYS: AoiKey[] = ["karrada", "bismayah"];

// Back-compat exports (Map's initial framing still references Karrada).
export const KARRADA_BBOX = AOIS.karrada.bbox;
export const KARRADA_CENTER = AOIS.karrada.center;
