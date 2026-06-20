"use client";

import { useStore } from "@/lib/store";
import { AGENT_COLOR, AGENT_LABEL, AGENTS } from "@/lib/colors";
import { AOIS, AOI_KEYS } from "@/lib/aoi";
import type { DetectionSet } from "@/lib/types";

// v1 = 10m optical index change sets (superseded). v2 = the validated high-res
// structural-change detector. Surfaced separately so the method story is clear.
const V1_SETS: { key: DetectionSet; label: string }[] = [
  { key: "full", label: "Full" },
  { key: "inland", label: "Inland" },
  { key: "recent", label: "Recent" },
];

const HIGHRES_SETS = ["highres", "highres_bismayah"];

export default function LayerFilter() {
  const activeAgents = useStore((s) => s.activeAgents);
  const toggleAgent = useStore((s) => s.toggleAgent);
  const setAllAgents = useStore((s) => s.setAllAgents);
  const detectionSet = useStore((s) => s.detectionSet);
  const setDetectionSet = useStore((s) => s.setDetectionSet);
  const showBuildings = useStore((s) => s.showBuildings);
  const toggleBuildings = useStore((s) => s.toggleBuildings);
  const aoi = useStore((s) => s.aoi);
  const setAoi = useStore((s) => s.setAoi);

  const allOn = AGENTS.every((a) => activeAgents[a]);
  const isKarrada = aoi === "karrada";
  const highresActive = HIGHRES_SETS.includes(detectionSet);

  return (
    <div className="fixed left-5 top-16 z-20 w-[196px] rounded-lg border border-border bg-surface/95 p-2.5 backdrop-blur">
      {/* AOI switcher — the same detector on two very different areas */}
      <div className="mb-2.5 border-b border-border pb-2.5">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
          Area
        </span>
        <div className="mt-1.5 grid grid-cols-2 gap-1">
          {AOI_KEYS.map((key) => {
            const active = aoi === key;
            return (
              <button
                key={key}
                onClick={() => setAoi(key)}
                title={AOIS[key].sublabel}
                className={`rounded border px-1.5 py-1 text-left transition-colors ${
                  active
                    ? "border-accent bg-accent/15 text-accent"
                    : "border-border text-muted hover:bg-surface-2"
                }`}
              >
                <div className="text-[11px] font-semibold leading-tight">
                  {AOIS[key].label}
                </div>
                <div className="text-[8px] uppercase tracking-wide opacity-70">
                  {AOIS[key].sublabel}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Base layer: every existing building (Karrada only — has footprints) */}
      {isKarrada && (
      <div className="mb-2.5 flex items-center justify-between border-b border-border pb-2.5">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
          Base
        </span>
        <button
          onClick={toggleBuildings}
          title="Toggle existing-building footprints (visible when zoomed in)"
          className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs transition-opacity ${
            showBuildings ? "" : "opacity-40"
          }`}
          style={{
            borderColor: showBuildings ? "#7891c4" : "#3a445e",
            color: showBuildings ? "#9fb4dd" : "#8a94ad",
          }}
        >
          <span
            className="h-2 w-2 rounded-[2px]"
            style={{
              background: showBuildings ? "#7891c4" : "transparent",
              border: "1px solid #7891c4",
            }}
          />
          Buildings
        </button>
      </div>
      )}

      {/* Agent layers as compact toggle chips */}
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
          Layers
        </span>
        <button
          onClick={() => setAllAgents(!allOn)}
          className="text-[10px] font-semibold text-muted hover:text-text"
        >
          {allOn ? "None" : "All"}
        </button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {AGENTS.map((a) => {
          const on = activeAgents[a];
          const color = AGENT_COLOR[a];
          return (
            <button
              key={a}
              onClick={() => toggleAgent(a)}
              title={`Toggle ${AGENT_LABEL[a]}`}
              className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs transition-opacity ${
                on ? "" : "opacity-40"
              }`}
              style={{
                borderColor: on ? color : "#3a445e",
                color: on ? color : "#8a94ad",
              }}
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{
                  background: on ? color : "transparent",
                  border: `1px solid ${color}`,
                }}
              />
              {AGENT_LABEL[a]}
            </button>
          );
        })}
      </div>

      {/* Detection set */}
      <div className="mt-2.5 border-t border-border pt-2.5">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted">
          Nova detections
        </span>

        {/* v2: the validated high-res method, given primacy */}
        <button
          onClick={() => setDetectionSet(AOIS[aoi].detectionSet)}
          title="High-resolution structural-change detection (validated method)"
          className={`mt-1.5 flex w-full items-center justify-between rounded border px-2 py-1.5 text-[11px] font-semibold transition-colors ${
            highresActive
              ? "border-accent bg-accent/20 text-accent"
              : "border-border text-muted hover:bg-surface-2"
          }`}
        >
          <span className="flex items-center gap-1.5">
            <span className="text-[13px] leading-none">◎</span>
            High-res change
          </span>
          <span className="rounded-sm bg-accent/15 px-1 text-[8px] uppercase tracking-wide text-accent">
            validated
          </span>
        </button>

        {/* v1: the superseded optical-index sets (Karrada only) */}
        {isKarrada && (
        <div className="mt-2 flex items-center gap-1.5">
          <span className="text-[9px] uppercase tracking-wide text-muted/70">
            v1 indices
          </span>
          <div className="flex flex-1 gap-1">
            {V1_SETS.map(({ key, label }) => {
              const active = detectionSet === key;
              return (
                <button
                  key={key}
                  onClick={() => setDetectionSet(key)}
                  title="10m optical index change (superseded by high-res)"
                  className={`flex-1 rounded border px-1 py-0.5 text-[10px] font-semibold transition-colors ${
                    active
                      ? "border-muted bg-surface-2 text-text"
                      : "border-border/60 text-muted/80 hover:bg-surface-2"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
        )}
      </div>
    </div>
  );
}
