import { NextResponse } from "next/server";

import { proxyResearch } from "@/lib/research-api/proxy";

/**
 * Auth-bound proxy for sealed scorecard artifact content (#357).
 * Session gate is middleware `/api/research/:path*`.
 */
export async function GET(
  request: Request,
  context: { params: Promise<{ scorecardId: string }> },
) {
  const { scorecardId } = await context.params;
  if (!scorecardId || scorecardId.includes("..") || scorecardId.includes("/")) {
    return NextResponse.json(
      { detail: { code: "not_found", message: "scorecard not found" } },
      { status: 404 },
    );
  }
  const url = new URL(request.url);
  const relativePath = url.searchParams.get("relative_path");
  if (!relativePath) {
    return NextResponse.json(
      {
        detail: {
          code: "not_allowlisted",
          message: "relative_path is required",
        },
      },
      { status: 400 },
    );
  }
  const qs = new URLSearchParams({ relative_path: relativePath });
  return proxyResearch(
    `/api/v1/research/scorecards/${encodeURIComponent(scorecardId)}/artifacts/content?${qs.toString()}`,
    { preserveContentType: true },
  );
}
