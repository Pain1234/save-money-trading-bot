import Link from "next/link";

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
      <p className="text-sm text-text-muted" data-testid="validation-list-empty">
        Noch keine Validierungsstudien erstellt.
      </p>
    );
  }

  return (
    <div
      className="overflow-x-auto rounded-xl border border-border-subtle"
      data-testid="validation-list-ready"
    >
      <table className="min-w-full text-left text-sm">
        <thead className="bg-bg-elevated text-text-muted">
          <tr>
            {[
              "Studie",
              "Strategie",
              "Status",
              "Fortschritt",
              "Entscheidung",
              "Erstellt",
            ].map((col) => (
              <th key={col} className="whitespace-nowrap px-3 py-2 font-medium">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.study_id} className="border-t border-border-subtle">
              <td className="px-3 py-2">
                <Link
                  href={`/dashboard/research/validation/${encodeURIComponent(item.study_id)}`}
                  className="text-mint hover:underline"
                >
                  {item.name}
                </Link>
              </td>
              <td className="px-3 py-2 font-mono text-xs">
                {displayValue(item.strategy_id)} · {displayValue(item.strategy_version)}
              </td>
              <td className="px-3 py-2">{STATUS_LABELS[item.status] ?? item.status}</td>
              <td className="px-3 py-2 text-xs">
                Rob {item.progress.robustness.completed}/{item.progress.robustness.total} ·
                Gates {item.progress.gates.pass}/{item.progress.gates.total}
              </td>
              <td className="px-3 py-2 text-xs">
                {item.decision ? OUTCOME_LABELS[item.decision.outcome] ?? item.decision.outcome : "Nicht verfügbar"}
              </td>
              <td className="px-3 py-2 font-mono text-xs">{displayValue(item.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
