"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Card } from "@/components/ui/Card";
import type {
  ValidationStudyDecision,
  ValidationStudyOutcome,
} from "@/lib/research-api/client";

interface ValidationStudyDecisionPanelProps {
  studyId: string;
  status: "open" | "decided";
  decision: ValidationStudyDecision | null;
}

const OUTCOME_OPTIONS: { value: ValidationStudyOutcome; label: string }[] = [
  { value: "accept", label: "Akzeptiert" },
  { value: "reject", label: "Abgelehnt" },
  { value: "inconclusive", label: "Nicht eindeutig" },
];

/**
 * Records the human-owned final decision for a Validation Study (#249).
 *
 * This is display/record-keeping only — it never triggers live/paper
 * promotion. The actual Strategy V1 decision remains #205.
 */
export function ValidationStudyDecisionPanel({
  studyId,
  status,
  decision,
}: ValidationStudyDecisionPanelProps) {
  const router = useRouter();
  const [outcome, setOutcome] = useState<ValidationStudyOutcome>("accept");
  const [rationale, setRationale] = useState("");
  const [decidedBy, setDecidedBy] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  if (status === "decided" || decision) {
    return null;
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    setFieldErrors({});
    if (!rationale.trim()) {
      setFieldErrors({ rationale: "Begründung ist erforderlich" });
      return;
    }
    setSubmitting(true);
    try {
      const resp = await fetch(
        `/api/research/validation/${encodeURIComponent(studyId)}/decision`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            outcome,
            rationale,
            decided_by: decidedBy || undefined,
          }),
        },
      );
      const body = await resp.json();
      if (!resp.ok) {
        setFieldErrors(body?.detail?.fields ?? {});
        setFormError(body?.detail?.message ?? "Entscheidung fehlgeschlagen");
        return;
      }
      router.refresh();
    } catch {
      setFormError("Netzwerkfehler beim Speichern der Entscheidung");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card padding="sm" data-testid="validation-decision-form">
      <h2 className="mb-3 text-sm font-medium">Finale Entscheidung erfassen</h2>
      <p className="mb-3 text-xs text-text-muted">
        Menschlich verantwortete Entscheidung — kein automatischer Trigger für
        Live/Paper-Promotion.
      </p>
      <form onSubmit={onSubmit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block text-text-muted">Ergebnis</span>
            <select
              value={outcome}
              onChange={(e) => setOutcome(e.target.value as ValidationStudyOutcome)}
              className="w-full rounded border border-border bg-bg-elevated px-2 py-1.5 text-sm"
              data-testid="validation-decision-outcome-select"
            >
              {OUTCOME_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-text-muted">Entschieden von</span>
            <input
              type="text"
              value={decidedBy}
              onChange={(e) => setDecidedBy(e.target.value)}
              placeholder="dashboard"
              className="w-full rounded border border-border bg-bg-elevated px-2 py-1.5 text-sm"
              data-testid="validation-decision-decided-by-input"
            />
          </label>
        </div>
        <label className="block text-sm">
          <span className="mb-1 block text-text-muted">Begründung</span>
          <textarea
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            rows={3}
            className="w-full rounded border border-border bg-bg-elevated px-2 py-1.5 text-sm"
            data-testid="validation-decision-rationale-input"
          />
          {fieldErrors.rationale && (
            <p className="mt-1 text-xs text-red-300">{fieldErrors.rationale}</p>
          )}
        </label>
        {formError && (
          <p className="text-sm text-red-300" data-testid="validation-decision-form-error">
            {formError}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-mint/20 px-3 py-1.5 text-sm text-mint disabled:opacity-50"
          data-testid="validation-decision-submit"
        >
          {submitting ? "Wird gespeichert…" : "Entscheidung speichern"}
        </button>
      </form>
    </Card>
  );
}
