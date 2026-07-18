import { proxyResearch } from "@/lib/research-api/proxy";

export async function POST(request: Request) {
  const body = await request.json();
  return proxyResearch("/api/v1/research/validation", {
    method: "POST",
    body,
  });
}
