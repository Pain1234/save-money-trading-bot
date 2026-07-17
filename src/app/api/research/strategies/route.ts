import { proxyResearch } from "@/lib/research-api/proxy";

export async function GET() {
  return proxyResearch("/api/v1/research/strategies");
}
