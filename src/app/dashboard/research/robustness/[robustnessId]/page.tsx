import Link from "next/link";
import { notFound } from "next/navigation";

import { RobustnessJobPanel } from "@/components/research/RobustnessJobPanel";
import { RobustnessManifestView } from "@/components/research/RobustnessManifestView";
import {
  ResearchApiError,
  ResearchPageHeader,
  rs,
} from "@/components/research/chrome/ResearchPageChrome";
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
      <div data-testid="robustness-detail-ready" className={rs.page}>
        <ResearchPageHeader
          title={detail.robustness_id}
          backHref="/dashboard/research/robustness"
          backLabel="← Robustheit"
          titleMono
        />
        <p className={rs.lead}>
          {TEST_TYPE_LABELS[detail.test_type] ?? detail.test_type} · Basis{" "}
          <Link
            href={`/dashboard/research/experiments/${encodeURIComponent(detail.base_experiment_id)}`}
            className="font-mono text-mint hover:underline"
          >
            {detail.base_experiment_id}
          </Link>
        </p>

        <RobustnessJobPanel robustnessId={detail.robustness_id} initial={detail} />

        <Card padding="sm">
          <h2 className={rs.sectionTitle}>Konfiguration</h2>
          <pre className="overflow-x-auto rounded-sm border border-border-subtle bg-bg-elevated p-2 text-[12px]">
            {JSON.stringify(detail.manifest?.config ?? {}, null, 2)}
          </pre>
          {detail.manifest?.base_run_id && (
            <p className={`mt-2 ${rs.muted}`}>
              Basis-Run:{" "}
              <span className="font-mono">{displayValue(detail.manifest.base_run_id)}</span>
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
      <ResearchApiError
        testId="robustness-detail-error"
        message={getResearchErrorMessage(error)}
      />
    );
  }
}
