"use client";

import { usePathname } from "next/navigation";

import { MonitorShell } from "@/components/layout/MonitorShell";
import { ResearchShell } from "@/components/research/shell/ResearchShell";
import { isResearchPath } from "@/lib/research/navigation";

interface DashboardChromeProps {
  username: string;
  children: React.ReactNode;
}

/**
 * Path-based chrome switch (#298).
 * Auth remains in the server DashboardLayout (`requireAuth`).
 */
export function DashboardChrome({ username, children }: DashboardChromeProps) {
  const pathname = usePathname();

  if (isResearchPath(pathname)) {
    return <ResearchShell username={username}>{children}</ResearchShell>;
  }

  return <MonitorShell username={username}>{children}</MonitorShell>;
}
