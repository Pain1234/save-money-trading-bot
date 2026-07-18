import Link from "next/link";

import { displayValue, type RobustnessJobSummary } from "@/lib/research-api/client";

interface RobustnessTableProps {
  items: RobustnessJobSummary[];
}

const TEST_TYPE_LABELS: Record<string, string> = {
  walk_forward: "Walk-Forward",
  cost_stress: "Cost Stress",
  parameter_stability: "Parameter Stability",
  bootstrap: "Bootstrap",
};

export function RobustnessTable({ items }: RobustnessTableProps) {
  if (items.length === 0) {
    return (
      <p className="text-sm text-text-muted" data-testid="robustness-list-empty">
        Noch keine Robustheitstests gestartet.
      </p>
    );
  }

  return (
    <div
      className="overflow-x-auto rounded-xl border border-border-subtle"
      data-testid="robustness-list-ready"
    >
      <table className="min-w-full text-left text-sm">
        <thead className="bg-bg-elevated text-text-muted">
          <tr>
            {["Test", "Basis-Experiment", "Status", "Erstellt", "Fehler"].map((col) => (
              <th key={col} className="whitespace-nowrap px-3 py-2 font-medium">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.robustness_id} className="border-t border-border-subtle">
              <td className="px-3 py-2">
                <Link
                  href={`/dashboard/research/robustness/${encodeURIComponent(item.robustness_id)}`}
                  className="text-mint hover:underline"
                >
                  {TEST_TYPE_LABELS[item.test_type] ?? item.test_type}
                </Link>
              </td>
              <td className="px-3 py-2">
                <Link
                  href={`/dashboard/research/experiments/${encodeURIComponent(item.base_experiment_id)}`}
                  className="font-mono text-xs text-mint hover:underline"
                >
                  {item.base_experiment_id}
                </Link>
              </td>
              <td className="px-3 py-2">{displayValue(item.status)}</td>
              <td className="px-3 py-2 font-mono text-xs">
                {displayValue(item.created_at)}
              </td>
              <td className="px-3 py-2 text-xs text-red-300">
                {displayValue(item.error)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
