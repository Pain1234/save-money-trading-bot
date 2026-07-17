import { proxyResearch } from "@/lib/research-api/proxy";

export async function GET(
  _request: Request,
  context: { params: Promise<{ experimentId: string }> },
) {
  const { experimentId } = await context.params;
  return proxyResearch(
    `/api/v1/research/experiments/${encodeURIComponent(experimentId)}/status`,
  );
}
