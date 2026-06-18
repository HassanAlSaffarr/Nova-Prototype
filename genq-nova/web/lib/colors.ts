import type { SourceAgent } from "./types";

// Per-agent palette, tuned to read clearly on the dark navy basemap.
export const AGENT_COLOR: Record<SourceAgent, string> = {
  nova: "#00ff9d", // neon green (brand accent)
  roberto: "#22d3ee", // cyan
  namroud: "#f59e0b", // amber
  peter: "#a78bfa", // violet
  data_chef: "#fb7185", // rose
};

export const AGENT_LABEL: Record<SourceAgent, string> = {
  nova: "Nova",
  roberto: "Roberto",
  namroud: "Namroud",
  peter: "Peter",
  data_chef: "Data Chef",
};

export const AGENT_LAYER_NAME: Record<SourceAgent, string> = {
  nova: "Geo-mapping",
  roberto: "Survey Intelligence",
  namroud: "Institutional Data",
  peter: "Social Listening",
  data_chef: "Expert Analysis",
};

export const AGENTS: SourceAgent[] = [
  "nova",
  "roberto",
  "namroud",
  "peter",
  "data_chef",
];

/** Hex "#rrggbb" → [r,g,b] for deck.gl color accessors. */
export function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
