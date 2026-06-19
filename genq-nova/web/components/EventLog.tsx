"use client";

import { useStore } from "@/lib/store";
import { AGENT_COLOR, AGENT_LABEL } from "@/lib/colors";
import { KARRADA_CENTER } from "@/lib/aoi";
import type { EventItem, SourceAgent } from "@/lib/types";

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function agentOf(a: string): SourceAgent {
  return (AGENT_COLOR[a as SourceAgent] ? a : "nova") as SourceAgent;
}

export default function EventLog() {
  const events = useStore((s) => s.events);
  const open = useStore((s) => s.eventLogOpen);
  const toggle = useStore((s) => s.toggleEventLog);
  const newEventId = useStore((s) => s.newEventId);
  const flyToFn = useStore((s) => s.flyToFn);

  const onEventClick = (ev: EventItem) => {
    // Events are AOI-level — pan to the scanned area (Karrada).
    if (ev.aoi === "karrada") flyToFn?.(KARRADA_CENTER[0], KARRADA_CENTER[1]);
  };

  return (
    <div className="fixed bottom-5 left-5 z-20 w-[340px] max-w-[88vw] overflow-hidden rounded-lg border border-border bg-surface/95 backdrop-blur">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">
            Event Log
          </span>
        </div>
        <button
          onClick={toggle}
          aria-label={open ? "Collapse" : "Expand"}
          className="rounded px-1.5 text-muted hover:bg-surface-2 hover:text-text"
        >
          {open ? "▾" : "▸"}
        </button>
      </div>

      {open && (
        <>
          {/* Events — Nova runs its loop autonomously; this is the live feed */}
          <div className="max-h-[340px] overflow-y-auto">
            {events.slice(0, 15).map((ev) => {
              const agent = agentOf(ev.agent);
              const color = AGENT_COLOR[agent];
              return (
                <button
                  key={ev.id}
                  onClick={() => onEventClick(ev)}
                  className={`flex w-full gap-2 border-b border-border/40 px-3 py-2 text-left last:border-0 hover:bg-surface-2 ${
                    ev.id === newEventId ? "event-flash" : ""
                  }`}
                >
                  <span
                    className="mt-1 h-2 w-2 shrink-0 rounded-full"
                    style={{ background: color }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span
                        className="text-[11px] font-semibold"
                        style={{ color }}
                      >
                        {AGENT_LABEL[agent]}
                      </span>
                      <span className="shrink-0 text-[10px] text-muted">
                        {fmtTime(ev.timestamp)}
                      </span>
                    </div>
                    <div className="text-xs leading-snug text-text/90">
                      {ev.message}
                    </div>
                  </div>
                </button>
              );
            })}
            {events.length === 0 && (
              <div className="px-3 py-4 text-center text-xs text-muted">
                No events yet.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
