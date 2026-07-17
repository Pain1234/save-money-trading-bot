import { Card } from "@/components/ui/Card";

export function SectionFallback({ label }: { label: string }) {
  return (
    <Card
      padding="sm"
      className="min-w-0 animate-pulse"
      data-testid={`section-loading-${label}`}
    >
      <p className="mb-2 text-[12px] text-text-muted">Lade {label}…</p>
      <div className="h-24 rounded bg-bg-elevated" />
    </Card>
  );
}
