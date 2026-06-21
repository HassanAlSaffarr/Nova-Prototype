"use client";

import { useEffect, useState } from "react";
import { useStore } from "@/lib/store";
import { API_BASE } from "@/lib/api";
import {
  AGENT_COLOR,
  AGENT_LABEL,
  AGENT_LAYER_NAME,
} from "@/lib/colors";
import type { Feature, SourceAgent } from "@/lib/types";

const CONFIDENCE_HELP =
  "Confidence = agent's certainty in this signal. Nova's high-res detector scores it from the strength of the structural-density jump; the older index method used NDBI/NDVI strength + area + footprint overlap. Synthetic agents use source-typical reliability.";

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

function Via({ agent }: { agent: SourceAgent }) {
  return (
    <span className="text-[10px]" style={{ color: `${AGENT_COLOR[agent]}cc` }}>
      via {AGENT_LABEL[agent]}
    </span>
  );
}

function Meta({
  label,
  value,
  agent,
}: {
  label: string;
  value: string;
  agent: SourceAgent;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] uppercase tracking-wide text-muted">
          {label}
        </span>
        <Via agent={agent} />
      </div>
      <div className="text-sm text-text">{value}</div>
    </div>
  );
}

function EsriThumb({ lat, lon }: { lat: number; lon: number }) {
  const [state, setState] = useState<"loading" | "ok" | "err">("loading");
  const src = `${API_BASE}/thumbnail?lat=${lat}&lon=${lon}`;

  useEffect(() => setState("loading"), [src]);

  if (state === "err") return null;
  return (
    <div className="relative h-[200px] w-full overflow-hidden rounded-lg border border-border bg-surface-2">
      {state === "loading" && (
        <div className="absolute inset-0 animate-pulse bg-surface-2" />
      )}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt="High-resolution view of this location"
        onLoad={() => setState("ok")}
        onError={() => setState("err")}
        className={`h-full w-full object-cover transition-opacity duration-300 ${
          state === "ok" ? "opacity-100" : "opacity-0"
        }`}
      />
      <span className="absolute bottom-1 right-1.5 rounded bg-black/50 px-1 text-[9px] text-white/70">
        Esri World Imagery
      </span>
    </div>
  );
}

function WaybackImg({
  lat,
  lon,
  date,
  label,
}: {
  lat: number;
  lon: number;
  date: string;
  label: string;
}) {
  const [state, setState] = useState<"loading" | "ok" | "err">("loading");
  const src = `${API_BASE}/wayback?lat=${lat}&lon=${lon}&date=${date}`;
  useEffect(() => setState("loading"), [src]);
  return (
    <div className="relative h-[150px] overflow-hidden rounded-lg border border-border bg-surface-2">
      {state !== "ok" && (
        <div className="absolute inset-0 grid place-items-center bg-surface-2 text-[10px] text-muted">
          {state === "loading" ? (
            <span className="animate-pulse">loading…</span>
          ) : (
            "imagery unavailable"
          )}
        </div>
      )}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={label}
        onLoad={() => setState("ok")}
        onError={() => setState("err")}
        className={`h-full w-full object-cover transition-opacity duration-300 ${
          state === "ok" ? "opacity-100" : "opacity-0"
        }`}
      />
      <span className="absolute left-1.5 top-1.5 rounded bg-black/55 px-1.5 py-0.5 text-[9px] font-semibold text-white">
        {label}
      </span>
    </div>
  );
}

// Before/after ~0.5m Wayback crops — the actual evidence behind a high-res
// detection (smooth/bare land → built structure).
function BeforeAfter({
  lat,
  lon,
  before,
  after,
}: {
  lat: number;
  lon: number;
  before: string;
  after: string;
}) {
  return (
    <div>
      <div className="grid grid-cols-2 gap-1.5">
        <WaybackImg lat={lat} lon={lon} date={before} label={`Before · ${before}`} />
        <WaybackImg lat={lat} lon={lon} date={after} label={`After · ${after}`} />
      </div>
      <div className="mt-1 text-right text-[9px] text-muted">
        Esri World Imagery Wayback
      </div>
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
  const isReal = agent === "nova";

  const related = (p?.related_ids ?? [])
    .map((id) => byId[id])
    .filter(Boolean) as Feature[];

  const isHighres = (p as Record<string, unknown> | undefined)?.method ===
    "highres";
  const novaExtras =
    agent !== "nova"
      ? []
      : isHighres
        ? [
            [
              "Type",
              { land_emergence: "Land emergence (river)", open_land: "Open land (desert)" }[
                (p as Record<string, unknown>)?.category as string
              ] ?? "Construction",
            ],
            ...(typeof (p as Record<string, unknown>)?.cnn_prob === "number"
              ? [
                  [
                    "Building (CNN)",
                    `${Math.round(
                      ((p as Record<string, unknown>).cnn_prob as number) * 100,
                    )}%`,
                  ] as [string, unknown],
                ]
              : []),
            ["Δ structure", p?.mean_delta],
            ["Cells flagged", p?.n_cells],
            ["Compared", `${p?.before} → ${p?.after}`],
          ]
        : [
            ["ΔNDVI", p?.delta_ndvi],
            ["ΔNDBI", p?.delta_ndbi],
            ["ΔBrightness", p?.delta_brightness],
            ["Overlaps footprint", p?.overlaps_footprint ? "Yes" : "No"],
          ];

  return (
    <aside
      className={`fixed right-0 top-0 z-30 h-full w-[420px] max-w-[90vw] transform overflow-y-auto border-l border-border bg-surface/95 backdrop-blur transition-transform duration-300 ease-out ${
        open ? "translate-x-0" : "translate-x-full"
      }`}
    >
      {feature && p && agent && (
        <div className="flex flex-col gap-5 p-5">
          {/* Top row: badge + type + close */}
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

          {/* Title + provenance */}
          <div>
            <h2 className="text-xl font-bold leading-tight text-text">
              {p.title_en}
            </h2>
            <p dir="rtl" className="mt-1 text-right text-sm text-muted">
              {p.title_ar}
            </p>
            <div className="mt-2 flex items-center gap-1.5">
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ background: isReal ? AGENT_COLOR.nova : "#8a94ad" }}
              />
              <span className="text-[11px] uppercase tracking-wide text-muted">
                {isReal
                  ? "Satellite-derived · real detection"
                  : "Synthetic signal · demo data"}
              </span>
            </div>
          </div>

          {/* High-res detections show the before/after evidence; everything
              else shows a single current high-res crop of the location. */}
          {isHighres && p.before && p.after ? (
            <BeforeAfter
              lat={Number(p.lat)}
              lon={Number(p.lon)}
              before={String(p.before)}
              after={String(p.after)}
            />
          ) : (
            <EsriThumb lat={Number(p.lat)} lon={Number(p.lon)} />
          )}

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
              <div className="mt-1">
                <Via agent={agent} />
              </div>
            </div>
          )}

          {/* Confidence — separated from the metric */}
          <div className="border-t border-border pt-4">
            <div className="mb-1 flex items-center justify-between text-xs text-muted">
              <span className="flex items-center gap-1.5">
                Confidence
                <span className="group relative inline-flex">
                  <span className="flex h-3.5 w-3.5 cursor-help items-center justify-center rounded-full border border-muted text-[9px] text-muted">
                    ?
                  </span>
                  <span className="pointer-events-none invisible absolute left-0 top-5 z-10 w-64 rounded-md border border-border bg-surface-2 p-2 text-[11px] leading-relaxed text-text/90 opacity-0 shadow-lg transition-opacity group-hover:visible group-hover:opacity-100">
                    {CONFIDENCE_HELP}
                  </span>
                </span>
              </span>
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
            <Meta label="Detected" value={fmtDate(p.timestamp)} agent={agent} />
            <Meta
              label="Coordinates"
              value={`${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`}
              agent={agent}
            />
            {p.area_m2 !== undefined && (
              <Meta
                label="Area"
                value={`${Number(p.area_m2).toLocaleString()} m²`}
                agent={agent}
              />
            )}
            <Meta label="Layer" value={AGENT_LAYER_NAME[agent]} agent={agent} />
          </div>

          {/* Nova extras */}
          {novaExtras.length > 0 && (
            <div className="grid grid-cols-2 gap-4 border-t border-border pt-4">
              {novaExtras.map(([label, val]) => (
                <Meta
                  key={String(label)}
                  label={String(label)}
                  value={String(val)}
                  agent={agent}
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
