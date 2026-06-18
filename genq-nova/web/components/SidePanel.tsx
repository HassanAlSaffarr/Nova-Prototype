"use client";

import { useEffect } from "react";
import { useStore } from "@/lib/store";
import {
  AGENT_COLOR,
  AGENT_LABEL,
  AGENT_LAYER_NAME,
} from "@/lib/colors";
import type { Feature, SourceAgent } from "@/lib/types";

function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmtValue(v: number): string {
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function AgentBadge({ agent }: { agent: SourceAgent }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold"
      style={{
        color: AGENT_COLOR[agent],
        background: `${AGENT_COLOR[agent]}1f`,
        border: `1px solid ${AGENT_COLOR[agent]}55`,
      }}
    >
      <span
        className="h-2 w-2 rounded-full"
        style={{ background: AGENT_COLOR[agent] }}
      />
      {AGENT_LABEL[agent]}
    </span>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-muted">
        {label}
      </div>
      <div className="text-sm text-text">{value}</div>
    </div>
  );
}

export default function SidePanel() {
  const selectedId = useStore((s) => s.selectedId);
  const byId = useStore((s) => s.byId);
  const select = useStore((s) => s.select);
  const selectRelated = useStore((s) => s.selectRelated);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") select(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [select]);

  const feature: Feature | undefined = selectedId ? byId[selectedId] : undefined;
  const open = !!feature;
  const p = feature?.properties;
  const agent = p?.source_agent as SourceAgent | undefined;
  const color = agent ? AGENT_COLOR[agent] : "#fff";
  const pct = p ? Math.round(p.confidence * 100) : 0;

  const related = (p?.related_ids ?? [])
    .map((id) => byId[id])
    .filter(Boolean) as Feature[];

  const novaExtras =
    agent === "nova"
      ? [
          ["ΔNDVI", p?.delta_ndvi],
          ["ΔNDBI", p?.delta_ndbi],
          ["ΔBrightness", p?.delta_brightness],
          [
            "Overlaps footprint",
            p?.overlaps_footprint ? "Yes" : "No",
          ],
        ]
      : [];

  return (
    <aside
      className={`fixed right-0 top-0 z-30 h-full w-[420px] max-w-[90vw] transform overflow-y-auto border-l border-border bg-surface/95 backdrop-blur transition-transform duration-300 ease-out ${
        open ? "translate-x-0" : "translate-x-full"
      }`}
    >
      {feature && p && agent && (
        <div className="flex flex-col gap-5 p-5">
          {/* Top row */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AgentBadge agent={agent} />
              <span className="text-xs text-muted">
                {titleCase(p.signal_type)}
              </span>
            </div>
            <button
              onClick={() => select(null)}
              aria-label="Close"
              className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text"
            >
              ✕
            </button>
          </div>

          {/* Title */}
          <div>
            <h2 className="text-xl font-bold leading-tight text-text">
              {p.title_en}
            </h2>
            <p dir="rtl" className="mt-1 text-right text-sm text-muted">
              {p.title_ar}
            </p>
          </div>

          {/* Hero metric */}
          {p.value !== null && p.value !== undefined && (
            <div className="rounded-lg border border-border bg-surface-2 px-4 py-3">
              <div className="text-3xl font-extrabold" style={{ color }}>
                {fmtValue(p.value)}
                {p.unit && (
                  <span className="ml-1.5 text-base font-medium text-muted">
                    {p.unit}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Confidence */}
          <div>
            <div className="mb-1 flex justify-between text-xs text-muted">
              <span>Confidence</span>
              <span style={{ color }}>{pct}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-surface-2">
              <div
                className="h-full rounded-full"
                style={{ width: `${pct}%`, background: color }}
              />
            </div>
          </div>

          {/* Summary */}
          <p className="text-sm leading-relaxed text-text/90">{p.summary}</p>

          {/* Metadata grid */}
          <div className="grid grid-cols-2 gap-4 border-t border-border pt-4">
            <Meta label="Detected" value={fmtDate(p.timestamp)} />
            <Meta
              label="Coordinates"
              value={`${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`}
            />
            {p.area_m2 !== undefined && (
              <Meta
                label="Area"
                value={`${Number(p.area_m2).toLocaleString()} m²`}
              />
            )}
            <Meta label="Layer" value={AGENT_LAYER_NAME[agent]} />
          </div>

          {/* Nova extras */}
          {novaExtras.length > 0 && (
            <div className="grid grid-cols-2 gap-4 border-t border-border pt-4">
              {novaExtras.map(([label, val]) => (
                <Meta
                  key={String(label)}
                  label={String(label)}
                  value={String(val)}
                />
              ))}
            </div>
          )}

          {/* Related signals */}
          {related.length > 0 && (
            <div className="border-t border-border pt-4">
              <div className="mb-2 text-[11px] uppercase tracking-wide text-muted">
                Related signals ({related.length})
              </div>
              <div className="flex flex-col gap-2">
                {related.map((r) => {
                  const ra = r.properties.source_agent as SourceAgent;
                  return (
                    <button
                      key={r.properties.id}
                      onClick={() => selectRelated(r.properties.id)}
                      className="flex items-center gap-2 rounded-md border border-border bg-surface-2 px-3 py-2 text-left hover:border-muted"
                    >
                      <span
                        className="h-2 w-2 shrink-0 rounded-full"
                        style={{ background: AGENT_COLOR[ra] }}
                      />
                      <span className="flex-1 text-sm text-text">
                        {r.properties.title_en}
                      </span>
                      <span className="text-xs text-muted">
                        {AGENT_LABEL[ra]}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Footer */}
          <div className="mt-2 flex items-center justify-between border-t border-border pt-3 text-[11px] text-muted">
            <span>Source: {AGENT_LABEL[agent]}</span>
            <span className="font-mono">{p.id}</span>
          </div>
        </div>
      )}
    </aside>
  );
}
