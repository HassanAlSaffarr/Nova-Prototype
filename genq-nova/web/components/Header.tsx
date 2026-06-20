"use client";

import { useStore } from "@/lib/store";
import { AOIS } from "@/lib/aoi";

export default function Header() {
  const aoi = useStore((s) => s.aoi);
  return (
    <header className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between px-5 py-3 pointer-events-none">
      <div className="flex items-baseline gap-3 pointer-events-auto">
        <span className="text-2xl font-extrabold tracking-tight text-text">
          NOVA
        </span>
        <span className="hidden sm:inline text-xs text-muted">
          GENQ Geo-Intelligence · {AOIS[aoi].label}, Baghdad
        </span>
      </div>
      <div className="flex items-center gap-2 pointer-events-auto">
        <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
        <span className="text-xs text-muted">live</span>
      </div>
    </header>
  );
}
