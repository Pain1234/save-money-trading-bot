import { ArchitectureDiagram } from "@/components/sidebar/ArchitectureDiagram";
import { ConceptLayers } from "@/components/sidebar/ConceptLayers";
import { SubdomainField } from "@/components/sidebar/SubdomainField";
import { TechStackGrid } from "@/components/sidebar/TechStackGrid";

export function Sidebar() {
  return (
    <aside className="space-y-2.5">
      <div>
        <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-text-primary">
          Hyperliquid Trading Bot
        </h1>
        <p className="mt-1.5 text-[13px] leading-relaxed text-text-secondary">
          Privates Dashboard für automatisiertes Perpetual-Trading auf
          Hyperliquid. Monitoring, Steuerung und Risikomanagement an einem Ort.
        </p>
      </div>

      <SubdomainField />
      <ConceptLayers />
      <ArchitectureDiagram />
      <TechStackGrid />
    </aside>
  );
}
