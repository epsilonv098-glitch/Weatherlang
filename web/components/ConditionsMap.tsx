"use client";
import { useEffect, useRef } from "react";
import L from "leaflet";
import { markerColor, valueLabel, type Loc, type Mode } from "@/lib/colors";

/** Leaflet + OpenStreetMap: one colored dot per place; tap a dot for details. */
export default function ConditionsMap({ locations, mode }: { locations: Loc[]; mode: Mode }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { scrollWheelZoom: false }).setView([10.45, 123.95], 9);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(m);
    layer.current = L.layerGroup().addTo(m);
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    layer.current?.clearLayers();
    for (const l of locations) {
      const href = `/place/${encodeURIComponent(l.location)}`;
      L.circleMarker([l.lat, l.lon], {
        radius: 13, color: "#ffffff", weight: 2, fillColor: markerColor(mode, l), fillOpacity: 0.92,
      })
        .bindPopup(`<strong>${l.location}</strong><br>${valueLabel(mode, l)}<br><a href="${href}">Open details</a>`)
        .addTo(layer.current!);
    }
  }, [locations, mode]);

  return (
    <div
      ref={el}
      role="application"
      aria-label="Map of Cebu showing current conditions by place"
      className="h-[55vh] min-h-[340px] w-full overflow-hidden rounded-2xl border border-[var(--border)]"
    />
  );
}
