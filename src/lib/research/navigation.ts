import type { NavItem } from "@/lib/dashboard/navigation";

export const WORKSPACE_NAV: NavItem[] = [
  { label: "Monitor", href: "/dashboard" },
  { label: "Research", href: "/dashboard/research" },
];

export const RESEARCH_NAV: NavItem[] = [
  { label: "Overview", href: "/dashboard/research" },
  { label: "Strategien", href: "/dashboard/research/strategies" },
  { label: "Experiments", href: "/dashboard/research/experiments" },
  { label: "Neues Experiment", href: "/dashboard/research/experiments/new" },
  { label: "Vergleich", href: "/dashboard/research/compare" },
];

export function isResearchPath(pathname: string | null): boolean {
  return Boolean(pathname?.startsWith("/dashboard/research"));
}
