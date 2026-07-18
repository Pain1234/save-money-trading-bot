import { proxyResearch } from "@/lib/research-api/proxy";

export async function GET(
  _request: Request,
  context: { params: Promise<{ robustnessId: string }> },
) {
  const { robustnessId } = await context.params;
  return proxyResearch(
    `/api/v1/research/robustness/${encodeURIComponent(robustnessId)}/status`,
  );
}
