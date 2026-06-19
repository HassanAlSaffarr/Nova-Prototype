"use client";

import { useStore } from "@/lib/store";
import { AGENT_COLOR, AGENT_LABEL, AGENTS } from "@/lib/colors";
import type { DetectionSet } from "@/lib/types";

const SETS: { key: DetectionSet; label: string }[] = [
  { key: "full", label: "Full" },
  { key: "inland", label: "Inland" },
  { key: "recent", label: "Recent" },
];

export default function LayerFilter() {
  const activeAgents = useStore((s) => s.activeAgents);
  const toggleAgent = useStore((s) => s.toggleAgent);
  const setAllAgents = useStore((s) => s.setAllAgents);
  const detectionSet = useStore((s) => s.detectionSet);
  const setDetectionSet = useStore((s) => s.setDetectionSet);
  const showBuildings = useStore((s) => s.showBuildings);
  const toggleBuildings = useStore((s) => s.toggleBuildings);

  const allOn = AGENTS.every((a) => activeAgents[a]);

  return (
    <div className="fixed left-5 top-16 z-20 w-[196px] rounded-lg border border-border bg-surface/95 p-2.5 backdrop-blur">
      {/* Base layer: every existing building (context beneath Nova's changes) */}
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
      <div className="mt-2.5 flex items-center gap-1.5 border-t border-border pt-2.5">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted">
          Nova
        </span>
        <div className="flex flex-1 gap-1">
          {SETS.map(({ key, label }) => {
            const active = detectionSet === key;
            return (
              <button
                key={key}
                onClick={() => setDetectionSet(key)}
                className={`flex-1 rounded border px-1 py-1 text-[11px] font-semibold transition-colors ${
                  active
                    ? "border-accent bg-accent/20 text-accent"
                    : "border-border text-muted hover:bg-surface-2"
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
