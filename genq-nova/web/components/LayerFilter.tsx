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
  const detectionSet = useStore((s) => s.detectionSet);
  const setDetectionSet = useStore((s) => s.setDetectionSet);

  return (
    <div className="fixed left-5 top-16 z-20 w-[210px] rounded-lg border border-border bg-surface/95 p-3 backdrop-blur">
      {/* Agent layers */}
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
        Layers
      </div>
      <div className="flex flex-col">
        {AGENTS.map((a) => {
          const on = activeAgents[a];
          const color = AGENT_COLOR[a];
          return (
            <button
              key={a}
              onClick={() => toggleAgent(a)}
              className="flex items-center gap-2 rounded px-1.5 py-1.5 hover:bg-surface-2"
            >
              <span
                className="h-3 w-3 shrink-0 rounded-full"
                style={{
                  background: on ? color : "transparent",
                  border: `1.5px solid ${on ? color : "#3a445e"}`,
                }}
              />
              <span
                className={`text-sm ${on ? "text-text" : "text-muted"}`}
              >
                {AGENT_LABEL[a]}
              </span>
            </button>
          );
        })}
      </div>

      {/* Detection set */}
      <div className="mt-3 border-t border-border pt-3">
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">
          Nova detections
        </div>
        <div className="flex gap-1">
          {SETS.map(({ key, label }) => {
            const active = detectionSet === key;
            return (
              <button
                key={key}
                onClick={() => setDetectionSet(key)}
                className={`flex-1 rounded-md border px-2 py-1.5 text-xs font-semibold transition-colors ${
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
