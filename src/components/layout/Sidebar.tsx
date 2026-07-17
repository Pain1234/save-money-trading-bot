"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { ArchitectureDiagram } from "@/components/sidebar/ArchitectureDiagram";
import { ConceptLayers } from "@/components/sidebar/ConceptLayers";
import { TechStackGrid } from "@/components/sidebar/TechStackGrid";
import { DETAIL_NAV } from "@/lib/dashboard/navigation";
import { RESEARCH_NAV, isResearchPath } from "@/lib/research/navigation";
import { cn } from "@/lib/utils";

export function Sidebar() {
  const pathname = usePathname();
  const research = isResearchPath(pathname);
  const nav = research ? RESEARCH_NAV : DETAIL_NAV;

  return (
    <aside className="space-y-2.5" data-testid="dashboard-sidebar">
      <div>
        <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-text-primary">
          {research ? "Research Workspace" : "Paper Trading Monitor"}
        </h1>
        <p className="mt-1.5 text-[13px] leading-relaxed text-text-secondary">
          {research
            ? "Read-only Ansicht über ExperimentRegistry und Run-Artefakte. Keine Start-, Cancel- oder Promotion-Aktionen."
            : "Read-only Dashboard für Paper-Trading auf Hyperliquid. Status, Positionen und Equity — ohne Order- oder Bot-Steuerung."}
        </p>
      </div>

      <div>
        <p className="mb-1.5 text-[11px] uppercase tracking-[0.05em] text-text-muted">
          {research ? "Research" : "Diagnose"}
        </p>
        <nav className="flex flex-col gap-1">
          {nav.map((item) => {
            const active =
              item.href === "/dashboard" || item.href === "/dashboard/research"
                ? pathname === item.href
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "rounded px-2 py-1 text-[12px] hover:bg-white/5",
                  active
                    ? "bg-mint/10 text-mint"
                    : "text-text-secondary hover:text-text-primary",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      {!research && (
        <>
          <ConceptLayers />
          <ArchitectureDiagram />
          <TechStackGrid />
        </>
      )}
    </aside>
  );
}
