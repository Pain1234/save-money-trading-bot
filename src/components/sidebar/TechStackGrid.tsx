import { TECH_STACK_ICONS } from "@/lib/mock-data";
import { Card } from "@/components/ui/Card";

export function TechStackGrid() {
  return (
    <Card padding="xs">
      <h3 className="mb-2 text-[12px] font-semibold tracking-wide text-text-primary">Tech Stack</h3>
      <div className="grid grid-cols-3 gap-1.5">
        {TECH_STACK_ICONS.map((tech) => (
          <div
            key={tech.name}
            className="flex flex-col items-center gap-1 rounded-md border border-border bg-bg-card-alt px-1.5 py-2"
          >
            <div
              className="flex h-6 w-6 items-center justify-center rounded text-[10px] font-semibold"
              style={{
                backgroundColor: `${tech.color}18`,
                color: tech.color,
              }}
            >
              {tech.abbr}
            </div>
            <span className="text-[9px] text-text-muted">{tech.name}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
