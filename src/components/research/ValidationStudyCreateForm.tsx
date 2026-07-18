"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Card } from "@/components/ui/Card";
import type { GateRunRecord, RobustnessJobSummary } from "@/lib/research-api/client";

export interface StudyExperimentOption {
  experiment_id: string;
  strategy_version: string;
  created_at: string;
}

interface ValidationStudyCreateFormProps {
  experiments: StudyExperimentOption[];
  robustnessJobs: RobustnessJobSummary[];
  gateRuns: GateRunRecord[];
}

function toggleId(ids: string[], id: string): string[] {
  return ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id];
}

export function ValidationStudyCreateForm({
  experiments,
  robustnessJobs,
  gateRuns,
}: ValidationStudyCreateFormProps) {
  const router = useRouter();
  const [experimentId, setExperimentId] = useState(
    experiments[0]?.experiment_id ?? "",
  );
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [robustnessIds, setRobustnessIds] = useState<string[]>([]);
  const [gateRunIds, setGateRunIds] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    setFieldErrors({});
    if (!experimentId) {
      setFieldErrors({ experiment_id: "Basis-Experiment ist erforderlich" });
      return;
    }
    setSubmitting(true);
    try {
      const resp = await fetch("/api/research/validation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name || undefined,
          experiment_id: experimentId,
          robustness_ids: robustnessIds,
          gate_run_ids: gateRunIds,
          notes,
        }),
      });
      const body = await resp.json();
      if (!resp.ok) {
        setFieldErrors(body?.detail?.fields ?? {});
        setFormError(body?.detail?.message ?? "Erstellen fehlgeschlagen");
        return;
      }
      const studyId = body.study_id as string;
      router.push(`/dashboard/research/validation/${encodeURIComponent(studyId)}`);
    } catch {
      setFormError("Netzwerkfehler beim Erstellen");
    } finally {
      setSubmitting(false);
    }
  }

  if (experiments.length === 0) {
    return (
      <Card padding="sm" data-testid="validation-create-empty">
        <p className="text-sm text-text-muted">
          Es gibt noch kein abgeschlossenes Experiment. Eine Validierungsstudie
          benötigt mindestens einen abgeschlossenen Basis-Lauf.
        </p>
      </Card>
    );
  }

  return (
    <Card padding="sm" data-testid="validation-create-form">
      <h2 className="mb-3 text-sm font-medium">Neue Validierungsstudie</h2>
      <form onSubmit={onSubmit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block text-text-muted">Basis-Experiment</span>
            <select
              value={experimentId}
              onChange={(e) => setExperimentId(e.target.value)}
              className="w-full rounded border border-border bg-bg-elevated px-2 py-1.5 text-sm font-mono"
              data-testid="validation-base-experiment-select"
            >
              {experiments.map((exp) => (
                <option key={exp.experiment_id} value={exp.experiment_id}>
                  {exp.experiment_id} ({exp.strategy_version})
                </option>
              ))}
            </select>
            {fieldErrors.experiment_id && (
              <p className="mt-1 text-xs text-red-300">{fieldErrors.experiment_id}</p>
            )}
          </label>

          <label className="text-sm">
            <span className="mb-1 block text-text-muted">Name (optional)</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z. B. Trend V1 Studie #1"
              className="w-full rounded border border-border bg-bg-elevated px-2 py-1.5 text-sm"
              data-testid="validation-name-input"
            />
          </label>
        </div>

        <fieldset className="rounded border border-border-subtle p-2">
          <legend className="px-1 text-xs text-text-muted">Robustheitstests</legend>
          {robustnessJobs.length === 0 ? (
            <p className="p-1 text-xs text-text-muted">
              Keine Robustheitstests verfügbar.
            </p>
          ) : (
            <div className="grid gap-1 sm:grid-cols-2">
              {robustnessJobs.map((job) => (
                <label
                  key={job.robustness_id}
                  className="flex items-center gap-2 text-xs"
                  data-testid={`validation-robustness-option-${job.robustness_id}`}
                >
                  <input
                    type="checkbox"
                    checked={robustnessIds.includes(job.robustness_id)}
                    onChange={() =>
                      setRobustnessIds((prev) => toggleId(prev, job.robustness_id))
                    }
                  />
                  <span className="font-mono">{job.robustness_id.slice(0, 20)}…</span>
                  <span className="text-text-muted">
                    {job.test_type} · {job.status}
                  </span>
                </label>
              ))}
            </div>
          )}
          {fieldErrors.robustness_ids && (
            <p className="mt-1 text-xs text-red-300">{fieldErrors.robustness_ids}</p>
          )}
        </fieldset>

        <fieldset className="rounded border border-border-subtle p-2">
          <legend className="px-1 text-xs text-text-muted">Gate-Ergebnisse</legend>
          {gateRuns.length === 0 ? (
            <p className="p-1 text-xs text-text-muted">Keine Gate-Ergebnisse verfügbar.</p>
          ) : (
            <div className="grid gap-1 sm:grid-cols-2">
              {gateRuns.map((gate) => (
                <label
                  key={gate.gate_run_id}
                  className="flex items-center gap-2 text-xs"
                  data-testid={`validation-gate-option-${gate.gate_run_id}`}
                >
                  <input
                    type="checkbox"
                    checked={gateRunIds.includes(gate.gate_run_id)}
                    onChange={() =>
                      setGateRunIds((prev) => toggleId(prev, gate.gate_run_id))
                    }
                  />
                  <span className="font-mono">{gate.gate_run_id.slice(0, 20)}…</span>
                  <span className="text-text-muted">
                    policy {gate.policy_version} · {gate.overall_status}
                  </span>
                </label>
              ))}
            </div>
          )}
          {fieldErrors.gate_run_ids && (
            <p className="mt-1 text-xs text-red-300">{fieldErrors.gate_run_ids}</p>
          )}
        </fieldset>

        <label className="block text-sm">
          <span className="mb-1 block text-text-muted">Notizen (optional)</span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="w-full rounded border border-border bg-bg-elevated px-2 py-1.5 text-sm"
            data-testid="validation-notes-input"
          />
        </label>

        {formError && (
          <p className="text-sm text-red-300" data-testid="validation-form-error">
            {formError}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-mint/20 px-3 py-1.5 text-sm text-mint disabled:opacity-50"
          data-testid="validation-submit"
        >
          {submitting ? "Wird erstellt…" : "Studie erstellen"}
        </button>
      </form>
    </Card>
  );
}
