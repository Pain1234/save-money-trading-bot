import Link from "next/link";

import { ArchitectureDiagram } from "@/components/sidebar/ArchitectureDiagram";
import { ConceptLayers } from "@/components/sidebar/ConceptLayers";
import { TechStackGrid } from "@/components/sidebar/TechStackGrid";
import { DETAIL_NAV } from "@/lib/dashboard/navigation";

export function Sidebar() {
  return (
    <aside className="space-y-2.5" data-testid="dashboard-sidebar">
      <div>
        <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-text-primary">
          Paper Trading Monitor
        </h1>
        <p className="mt-1.5 text-[13px] leading-relaxed text-text-secondary">
          Read-only Dashboard für Paper-Trading auf Hyperliquid. Status,
          Positionen und Equity — ohne Order- oder Bot-Steuerung.
        </p>
      </div>

      <div>
        <p className="mb-1.5 text-[11px] uppercase tracking-[0.05em] text-text-muted">
          Diagnose
        </p>
        <nav className="flex flex-col gap-1">
          {DETAIL_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded px-2 py-1 text-[12px] text-text-secondary hover:bg-white/5 hover:text-text-primary"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </div>

      <ConceptLayers />
      <ArchitectureDiagram />
      <TechStackGrid />
    </aside>
  );
}
