"use client";

import { useState } from "react";
import { useStore } from "@/lib/store";
import { AGENT_COLOR, AGENT_LABEL, AGENTS } from "@/lib/colors";
import { AOIS, AOI_KEYS } from "@/lib/aoi";
import type { DetectionSet } from "@/lib/types";

// "High-res" = the validated v2 detector (all AOIs at once). Full/Inland/Recent
// are the superseded v1 optical-index sets, tucked behind the Method expander.
const METHODS: { key: DetectionSet; label: string; legacy?: boolean }[] = [
  { key: "highres", label: "High-res" },
  { key: "full", label: "Full", legacy: true },
  { key: "inland", label: "Inland", legacy: true },
  { key: "recent", label: "Recent", legacy: true },
];

const NON_CONSTRUCTION = "#9ca3af";

export default function LayerFilter() {
  const activeAgents = useStore((s) => s.activeAgents);
  const toggleAgent = useStore((s) => s.toggleAgent);
  const setAllAgents = useStore((s) => s.setAllAgents);
  const detectionSet = useStore((s) => s.detectionSet);
  const setDetectionSet = useStore((s) => s.setDetectionSet);
  const showBuildings = useStore((s) => s.showBuildings);
  const toggleBuildings = useStore((s) => s.toggleBuildings);
  const constructionOnly = useStore((s) => s.constructionOnly);
  const toggleConstructionOnly = useStore((s) => s.toggleConstructionOnly);
  const aoi = useStore((s) => s.aoi);
  const focusAoi = useStore((s) => s.focusAoi);

  const [methodOpen, setMethodOpen] = useState(false);
  const allOn = AGENTS.every((a) => activeAgents[a]);
  const activeMethod = METHODS.find((m) => m.key === detectionSet) ?? METHODS[0];

  return (
    <div className="fixed left-5 top-16 z-20 w-[196px] rounded-lg border border-border bg-surface/95 p-2.5 backdrop-blur">
      {/* Fly-to focus — all areas render at once; this just moves the camera */}
      <div className="mb-2.5 border-b border-border pb-2.5">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
          Fly to
        </span>
        <div className="mt-1.5 grid grid-cols-2 gap-1">
          {AOI_KEYS.map((key) => (
            <button
              key={key}
              onClick={() => focusAoi(key)}
              title={AOIS[key].sublabel}
              className={`rounded border px-1.5 py-1 text-left transition-colors ${
                aoi === key
                  ? "border-accent/70 bg-accent/10 text-text"
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
          ))}
        </div>
      </div>

      {/* Base layer: existing-building footprints */}
      <div className="mb-2.5 flex items-center justify-between border-b border-border pb-2.5">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
          Base
        </span>
        <button
          onClick={toggleBuildings}
          title="Toggle existing-building footprints"
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

      {/* Nova detections: a compact legend + a collapsed method picker */}
      <div className="mt-2.5 border-t border-border pt-2.5">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted">
          Nova detections
        </span>
        <div className="mt-1 flex items-center gap-3 text-[10px] text-muted">
          <span className="flex items-center gap-1">
            <span
              className="h-2 w-2 rounded-full"
              style={{ border: `1.5px solid ${AGENT_COLOR.nova}` }}
            />
            construction
          </span>
          <span className="flex items-center gap-1">
            <span
              className="h-2 w-2 rounded-full"
              style={{ border: `1.5px solid ${NON_CONSTRUCTION}` }}
            />
            other change
          </span>
        </div>

        {/* Demo lever: hide the lower-confidence non-construction sites */}
        <button
          onClick={toggleConstructionOnly}
          className={`mt-2 flex w-full items-center justify-between rounded border px-2 py-1 text-[10px] font-semibold transition-colors ${
            constructionOnly
              ? "border-accent bg-accent/15 text-accent"
              : "border-border text-muted hover:bg-surface-2"
          }`}
        >
          Construction only
          <span>{constructionOnly ? "on" : "off"}</span>
        </button>

        <button
          onClick={() => setMethodOpen((o) => !o)}
          className="mt-2 flex w-full items-center justify-between text-[10px] text-muted/80 hover:text-text"
        >
          <span>
            Method: <span className="text-text">{activeMethod.label}</span>
            {activeMethod.legacy && (
              <span className="ml-1 text-muted/60">(legacy v1)</span>
            )}
          </span>
          <span>{methodOpen ? "▾" : "▸"}</span>
        </button>
        {methodOpen && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {METHODS.map(({ key, label, legacy }) => (
              <button
                key={key}
                onClick={() => setDetectionSet(key)}
                title={legacy ? "Superseded 10m optical index set" : "Validated high-res detector"}
                className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold transition-colors ${
                  detectionSet === key
                    ? "border-accent bg-accent/15 text-accent"
                    : "border-border/60 text-muted/80 hover:bg-surface-2"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
