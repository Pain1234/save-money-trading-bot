import { StrategyDetailError, StrategyDetailView } from "@/components/research/StrategyDetailView";
import { fetchPaperApi, PaperApiError } from "@/lib/paper-api/client";
import { getResearchErrorMessage } from "@/lib/research-api/client";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

interface StrategyDetail {
  strategy_id: string;
  display_name: string;
  description: string;
  strategy_version: string;
  aliases: string[];
  lifecycle_status: string;
  supported_symbols: string[];
  required_timeframes: string[];
  monthly_filter: string;
  weekly_filter: string;
  daily_entries: string;
  stop_logic: string;
  reason_codes: string[];
  parameter_defaults: Record<string, unknown>;
  parameter_descriptions: Record<string, string>;
  experiment_count: number;
  last_run: {
    experiment_id?: string;
    status?: string;
    created_at?: string;
  } | null;
  experiments: Array<{
    experiment_id?: string;
    status?: string;
    created_at?: string;
    net_pnl?: string | null;
  }>;
}

export default async function ResearchStrategyDetailPage({
  params,
}: {
  params: Promise<{ strategyId: string }>;
}) {
  const { strategyId } = await params;

  try {
    const strategy = await fetchPaperApi<StrategyDetail>(
      `/api/v1/research/strategies/${encodeURIComponent(strategyId)}`,
      { noStore: true },
    );

    return <StrategyDetailView strategy={strategy} />;
  } catch (error) {
    if (error instanceof PaperApiError && error.status === 404) {
      notFound();
    }
    return <StrategyDetailError message={getResearchErrorMessage(error)} />;
  }
}
