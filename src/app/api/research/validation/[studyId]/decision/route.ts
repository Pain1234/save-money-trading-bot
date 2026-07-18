import { proxyResearch } from "@/lib/research-api/proxy";

export async function POST(
  request: Request,
  context: { params: Promise<{ studyId: string }> },
) {
  const { studyId } = await context.params;
  const body = await request.json();
  return proxyResearch(
    `/api/v1/research/validation/${encodeURIComponent(studyId)}/decision`,
    { method: "POST", body },
  );
}
