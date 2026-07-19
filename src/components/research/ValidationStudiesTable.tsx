import Link from "next/link";

import {
  ResearchTableFrame,
  rs,
} from "@/components/research/chrome/ResearchPageChrome";
import { displayValue, type ValidationStudyDetail } from "@/lib/research-api/client";

interface ValidationStudiesTableProps {
  items: ValidationStudyDetail[];
}

const STATUS_LABELS: Record<string, string> = {
  open: "Offen",
  decided: "Entschieden",
};

const OUTCOME_LABELS: Record<string, string> = {
  accept: "Akzeptiert",
  reject: "Abgelehnt",
  inconclusive: "Nicht eindeutig",
};

export function ValidationStudiesTable({ items }: ValidationStudiesTableProps) {
  if (items.length === 0) {
    return (
      <p className={rs.muted} data-testid="validation-list-empty">
        Noch keine Validierungsstudien erstellt.
      </p>
    );
  }

  return (
    <ResearchTableFrame testId="validation-list-ready">
      <table className={rs.table}>
        <thead>
          <tr>
            {[
              "Studie",
              "Strategie",
              "Status",
              "Fortschritt",
              "Entscheidung",
              "Erstellt",
            ].map((col) => (
              <th key={col} className={`whitespace-nowrap ${rs.th}`}>
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.study_id} className="border-t border-border-subtle">
              <td className={rs.td}>
                <Link
                  href={`/dashboard/research/validation/${encodeURIComponent(item.study_id)}`}
                  className="text-mint hover:underline"
                >
                  {item.name}
                </Link>
              </td>
              <td className={`${rs.td} font-mono text-[11px]`}>
                {displayValue(item.strategy_id)} · {displayValue(item.strategy_version)}
              </td>
              <td className={rs.td}>{STATUS_LABELS[item.status] ?? item.status}</td>
              <td className={`${rs.td} text-[11px]`}>
                Rob {item.progress.robustness.completed}/{item.progress.robustness.total} ·
                Gates {item.progress.gates.pass}/{item.progress.gates.total}
              </td>
              <td className={`${rs.td} text-[11px]`}>
                {item.decision ? OUTCOME_LABELS[item.decision.outcome] ?? item.decision.outcome : "Nicht verfügbar"}
              </td>
              <td className={`${rs.td} font-mono text-[11px]`}>{displayValue(item.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ResearchTableFrame>
  );
}
