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
  { label: "Robustheit", href: "/dashboard/research/robustness" },
  { label: "Validierung", href: "/dashboard/research/validation" },
];

export function isResearchPath(pathname: string | null): boolean {
  return Boolean(pathname?.startsWith("/dashboard/research"));
}

/** Active-state for Research sidebar/top section links (#298). */
export function isResearchNavActive(
  pathname: string | null,
  href: string,
): boolean {
  if (!pathname) return false;
  if (href === "/dashboard/research") {
    return pathname === href;
  }
  if (href === "/dashboard/research/experiments") {
    return (
      pathname === href ||
      (pathname.startsWith(`${href}/`) &&
        !pathname.startsWith("/dashboard/research/experiments/new"))
    );
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}
