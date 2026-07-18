import Link from "next/link";
import { notFound } from "next/navigation";

import { RobustnessJobPanel } from "@/components/research/RobustnessJobPanel";
import { RobustnessManifestView } from "@/components/research/RobustnessManifestView";
import { Card } from "@/components/ui/Card";
import { PaperApiError } from "@/lib/paper-api/client";
import {
  displayValue,
  fetchRobustnessJob,
  getResearchErrorMessage,
} from "@/lib/research-api/client";

export const dynamic = "force-dynamic";

const TEST_TYPE_LABELS: Record<string, string> = {
  walk_forward: "Walk-Forward",
  cost_stress: "Cost Stress",
  parameter_stability: "Parameter Stability",
  bootstrap: "Bootstrap / Monte Carlo",
};

export default async function ResearchRobustnessDetailPage({
  params,
}: {
  params: Promise<{ robustnessId: string }>;
}) {
  const { robustnessId } = await params;

  try {
    const detail = await fetchRobustnessJob(robustnessId);

    return (
      <div data-testid="robustness-detail-ready" className="space-y-4">
        <div>
          <Link
            href="/dashboard/research/robustness"
            className="text-xs text-text-muted hover:text-mint"
          >
            ← Robustheit
          </Link>
          <h1 className="mt-2 font-mono text-xl font-semibold">
            {detail.robustness_id}
          </h1>
          <p className="mt-1 text-sm text-text-secondary">
            {TEST_TYPE_LABELS[detail.test_type] ?? detail.test_type} · Basis{" "}
            <Link
              href={`/dashboard/research/experiments/${encodeURIComponent(detail.base_experiment_id)}`}
              className="font-mono text-mint hover:underline"
            >
              {detail.base_experiment_id}
            </Link>
          </p>
        </div>

        <RobustnessJobPanel robustnessId={detail.robustness_id} initial={detail} />

        <Card padding="sm">
          <h2 className="mb-3 text-sm font-medium">Konfiguration</h2>
          <pre className="overflow-x-auto rounded border border-border-subtle bg-bg-elevated p-2 text-xs">
            {JSON.stringify(detail.manifest?.config ?? {}, null, 2)}
          </pre>
          {detail.manifest?.base_run_id && (
            <p className="mt-2 text-xs text-text-muted">
              Basis-Run: <span className="font-mono">{displayValue(detail.manifest.base_run_id)}</span>
            </p>
          )}
        </Card>

        <RobustnessManifestView manifest={detail.manifest} />
      </div>
    );
  } catch (error) {
    if (error instanceof PaperApiError && error.status === 404) {
      notFound();
    }
    return (
      <div
        data-testid="robustness-detail-error"
        className="rounded-xl border border-red-500/40 bg-red-500/10 p-6"
      >
        <h1 className="text-xl font-semibold text-red-300">Research API Error</h1>
        <p className="mt-2 text-sm text-red-200/90">
          {getResearchErrorMessage(error)}
        </p>
      </div>
    );
  }
}
