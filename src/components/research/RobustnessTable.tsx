import Link from "next/link";

import {
  ResearchTableFrame,
  rs,
} from "@/components/research/chrome/ResearchPageChrome";
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
      <p className={rs.muted} data-testid="robustness-list-empty">
        Noch keine Robustheitstests gestartet.
      </p>
    );
  }

  return (
    <ResearchTableFrame testId="robustness-list-ready">
      <table className={rs.table}>
        <thead>
          <tr>
            {["Test", "Basis-Experiment", "Status", "Erstellt", "Fehler"].map((col) => (
              <th key={col} className={`whitespace-nowrap ${rs.th}`}>
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.robustness_id} className="border-t border-border-subtle">
              <td className={rs.td}>
                <Link
                  href={`/dashboard/research/robustness/${encodeURIComponent(item.robustness_id)}`}
                  className="text-mint hover:underline"
                >
                  {TEST_TYPE_LABELS[item.test_type] ?? item.test_type}
                </Link>
              </td>
              <td className={rs.td}>
                <Link
                  href={`/dashboard/research/experiments/${encodeURIComponent(item.base_experiment_id)}`}
                  className="font-mono text-[11px] text-mint hover:underline"
                >
                  {item.base_experiment_id}
                </Link>
              </td>
              <td className={rs.td}>{displayValue(item.status)}</td>
              <td className={`${rs.td} font-mono text-[11px]`}>
                {displayValue(item.created_at)}
              </td>
              <td className={`${rs.td} text-[11px] text-red-300`}>
                {displayValue(item.error)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </ResearchTableFrame>
  );
}
