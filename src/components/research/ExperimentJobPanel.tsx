"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Card } from "@/components/ui/Card";
import { displayValue } from "@/lib/research-api/client";
import { isActiveJobStatus } from "@/lib/research/lab-validation";

interface JobStatusPayload {
  status: string;
  started_at: string | null;
  finished_at: string | null;
  elapsed_seconds: number | null;
  error: string | null;
  error_detail: string | null;
  worker_alive?: boolean;
}

interface ExperimentJobPanelProps {
  experimentId: string;
  initialJob: JobStatusPayload | null;
}

export function ExperimentJobPanel({
  experimentId,
  initialJob,
}: ExperimentJobPanelProps) {
  const router = useRouter();
  const [job, setJob] = useState<JobStatusPayload | null>(initialJob);

  useEffect(() => {
    if (!job || !isActiveJobStatus(job.status)) return;
    const id = window.setInterval(async () => {
      try {
        const resp = await fetch(
          `/api/research/experiments/${encodeURIComponent(experimentId)}/status`,
        );
        if (!resp.ok) return;
        const body = (await resp.json()) as JobStatusPayload;
        setJob(body);
        if (body.status === "completed" || body.status === "failed") {
          router.refresh();
        }
      } catch {
        /* ignore transient poll errors */
      }
    }, 2000);
    return () => window.clearInterval(id);
  }, [experimentId, job?.status, router]);

  if (!job) return null;

  return (
    <Card padding="sm" data-testid="research-job-panel">
      <h2 className="mb-3 text-sm font-medium">Job-Status</h2>
      <dl className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-text-muted">
            Status
          </dt>
          <dd className="mt-0.5 font-mono" data-testid="research-job-status">
            {job.status}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-text-muted">
            Startzeit
          </dt>
          <dd className="mt-0.5 font-mono text-xs">
            {displayValue(job.started_at)}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-text-muted">
            Laufzeit
          </dt>
          <dd className="mt-0.5 font-mono">
            {job.elapsed_seconds == null
              ? "Nicht verfügbar"
              : `${Math.round(job.elapsed_seconds)}s`}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-text-muted">
            Worker
          </dt>
          <dd className="mt-0.5 text-xs">
            {job.worker_alive ? "aktiv" : "nicht aktiv"}
          </dd>
        </div>
      </dl>

      {isActiveJobStatus(job.status) && (
        <p className="mt-3 text-sm text-text-secondary">
          Lauf wird aktualisiert… Metriken erscheinen nach Abschluss.
        </p>
      )}

      {job.status === "failed" && (
        <div className="mt-3 space-y-2" data-testid="research-job-failed">
          <p className="text-sm text-red-300">
            {displayValue(job.error)}
          </p>
          {job.error_detail && (
            <details className="rounded border border-border-subtle p-2 text-xs">
              <summary className="cursor-pointer text-text-muted">
                Technische Details
              </summary>
              <pre className="mt-2 whitespace-pre-wrap font-mono text-text-secondary">
                {job.error_detail}
              </pre>
            </details>
          )}
        </div>
      )}
    </Card>
  );
}
