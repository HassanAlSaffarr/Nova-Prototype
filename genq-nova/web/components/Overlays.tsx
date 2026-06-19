"use client";

import { useStore } from "@/lib/store";
import { AGENTS } from "@/lib/colors";

function LoadingOverlay() {
  return (
    <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center">
      <div className="flex items-center gap-3 rounded-lg border border-border bg-surface/90 px-5 py-3 backdrop-blur">
        <span className="relative flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-accent" />
        </span>
        <span className="text-sm text-muted">Loading Karrada signals…</span>
      </div>
    </div>
  );
}

function ErrorBanner({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="absolute left-1/2 top-3 z-40 flex max-w-[90vw] -translate-x-1/2 items-center gap-3 rounded-md border border-red-500/40 bg-red-950/85 px-4 py-2 text-sm text-red-200 backdrop-blur">
      <span>
        Can&apos;t reach Nova API at :8000 — make sure the backend is running.
      </span>
      <button
        onClick={onDismiss}
        aria-label="Dismiss"
        className="shrink-0 text-red-300 hover:text-white"
      >
        ✕
      </button>
    </div>
  );
}

function EmptyHint() {
  return (
    <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
      <div className="rounded-lg border border-border bg-surface/80 px-5 py-3 text-sm text-muted backdrop-blur">
        All layers hidden — toggle one back on to see signals.
      </div>
    </div>
  );
}

export default function Overlays() {
  const loading = useStore((s) => s.loading);
  const error = useStore((s) => s.error);
  const clearError = useStore((s) => s.clearError);
  const activeAgents = useStore((s) => s.activeAgents);

  const allOff = AGENTS.every((a) => !activeAgents[a]);

  return (
    <>
      {loading && <LoadingOverlay />}
      {error && <ErrorBanner onDismiss={clearError} />}
      {!loading && !error && allOff && <EmptyHint />}
    </>
  );
}
