import { proxyResearch } from "@/lib/research-api/proxy";

export async function GET(
  request: Request,
  context: { params: Promise<{ experimentId: string }> },
) {
  const { experimentId } = await context.params;
  const url = new URL(request.url);
  const qs = url.searchParams.toString();
  return proxyResearch(
    `/api/v1/research/experiments/${encodeURIComponent(experimentId)}/chart-data${
      qs ? `?${qs}` : ""
    }`,
  );
}
