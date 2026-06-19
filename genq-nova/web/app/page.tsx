"use client";

import dynamic from "next/dynamic";
import Header from "@/components/Header";
import SidePanel from "@/components/SidePanel";
import EventLog from "@/components/EventLog";
import LayerFilter from "@/components/LayerFilter";

// Map uses maplibre/deck.gl (browser-only) — load without SSR.
const Map = dynamic(() => import("@/components/Map"), { ssr: false });

export default function Page() {
  return (
    <main className="relative h-screen w-screen bg-bg">
      <Header />
      <Map />
      <LayerFilter />
      <EventLog />
      <SidePanel />
    </main>
  );
}
