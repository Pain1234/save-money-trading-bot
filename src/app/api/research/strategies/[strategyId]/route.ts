import { proxyResearch } from "@/lib/research-api/proxy";

export async function GET(
  _request: Request,
  context: { params: Promise<{ strategyId: string }> },
) {
  const { strategyId } = await context.params;
  return proxyResearch(
    `/api/v1/research/strategies/${encodeURIComponent(strategyId)}`,
  );
}
