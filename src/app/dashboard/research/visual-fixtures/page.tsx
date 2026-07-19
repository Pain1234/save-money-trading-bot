import { notFound } from "next/navigation";

import { ResearchOverviewView } from "@/components/research/ResearchOverviewView";
import {
  overviewFixture,
  type OverviewFixtureScenario,
} from "@/lib/research/overview-fixtures";

export const dynamic = "force-dynamic";

const ALLOWED = new Set<OverviewFixtureScenario>([
  "ready",
  "legacy",
  "invalidated",
]);

/**
 * Synthetic Overview chrome for visual regression (#358).
 * Enabled only when ALLOW_RESEARCH_VISUAL_FIXTURES=1 (Playwright / local).
 */
export default async function ResearchOverviewVisualFixturesPage({
  searchParams,
}: {
  searchParams: Promise<{ scenario?: string }>;
}) {
  if (process.env.ALLOW_RESEARCH_VISUAL_FIXTURES !== "1") {
    notFound();
  }
  const params = await searchParams;
  const scenario = (params.scenario ?? "legacy") as OverviewFixtureScenario;
  if (!ALLOWED.has(scenario)) {
    notFound();
  }
  const fixture = overviewFixture(scenario);
  return (
    <div data-testid="research-overview-visual-fixture" data-scenario={scenario}>
      <ResearchOverviewView {...fixture} />
    </div>
  );
}
