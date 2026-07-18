"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Card } from "@/components/ui/Card";
import { displayValue, type RobustnessJobDetail } from "@/lib/research-api/client";
import { isActiveJobStatus } from "@/lib/research/lab-validation";

interface StatusPayload {
  status: string;
  started_at: string | null;
  finished_at: string | null;
  elapsed_seconds: number | null;
  error: string | null;
  error_detail: string | null;
  worker_alive?: boolean;
}

interface RobustnessJobPanelProps {
  robustnessId: string;
  initial: RobustnessJobDetail;
}

export function RobustnessJobPanel({ robustnessId, initial }: RobustnessJobPanelProps) {
  const router = useRouter();
  const [status, setStatus] = useState<StatusPayload>({
    status: initial.status,
    started_at: initial.started_at,
    finished_at: initial.finished_at,
    elapsed_seconds: initial.elapsed_seconds,
    error: initial.error,
    error_detail: initial.error_detail,
    worker_alive: initial.worker_alive,
  });

  useEffect(() => {
    if (!isActiveJobStatus(status.status)) return;
    const id = window.setInterval(async () => {
      try {
        const resp = await fetch(
          `/api/research/robustness/${encodeURIComponent(robustnessId)}/status`,
        );
        if (!resp.ok) return;
        const body = (await resp.json()) as StatusPayload;
        setStatus(body);
        if (body.status === "completed" || body.status === "failed") {
          router.refresh();
        }
      } catch {
        /* ignore transient poll errors */
      }
    }, 2000);
    return () => window.clearInterval(id);
  }, [robustnessId, status.status, router]);

  return (
    <Card padding="sm" data-testid="robustness-job-panel">
      <h2 className="mb-3 text-sm font-medium">Job-Status</h2>
      <dl className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-text-muted">Status</dt>
          <dd className="mt-0.5 font-mono" data-testid="robustness-job-status">
            {status.status}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-text-muted">Startzeit</dt>
          <dd className="mt-0.5 font-mono text-xs">{displayValue(status.started_at)}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-text-muted">Laufzeit</dt>
          <dd className="mt-0.5 font-mono">
            {status.elapsed_seconds == null
              ? "Nicht verfügbar"
              : `${Math.round(status.elapsed_seconds)}s`}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-text-muted">Worker</dt>
          <dd className="mt-0.5 text-xs">{status.worker_alive ? "aktiv" : "nicht aktiv"}</dd>
        </div>
      </dl>

      {isActiveJobStatus(status.status) && (
        <p className="mt-3 text-sm text-text-secondary">
          Robustheitstest läuft… Ergebnisse erscheinen nach Abschluss.
        </p>
      )}

      {status.error && (
        <div className="mt-3 space-y-2" data-testid="robustness-job-error">
          <p className="text-sm text-amber-300">{displayValue(status.error)}</p>
          {status.error_detail && (
            <details className="rounded border border-border-subtle p-2 text-xs">
              <summary className="cursor-pointer text-text-muted">
                Technische Details
              </summary>
              <pre className="mt-2 whitespace-pre-wrap font-mono text-text-secondary">
                {status.error_detail}
              </pre>
            </details>
          )}
        </div>
      )}
    </Card>
  );
}
