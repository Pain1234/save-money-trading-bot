import type { NavItem } from "@/lib/dashboard/navigation";

export const WORKSPACE_NAV: NavItem[] = [
  { label: "Monitor", href: "/dashboard" },
  { label: "Research", href: "/dashboard/research" },
];

export const RESEARCH_NAV: NavItem[] = [
  { label: "Overview", href: "/dashboard/research" },
  { label: "Experiments", href: "/dashboard/research/experiments" },
];

export function isResearchPath(pathname: string | null): boolean {
  return Boolean(pathname?.startsWith("/dashboard/research"));
}
