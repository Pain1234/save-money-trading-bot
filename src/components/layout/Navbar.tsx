"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { LogoutButton } from "@/components/monitor/LogoutButton";
import { PRIMARY_NAV } from "@/lib/dashboard/navigation";
import { RESEARCH_NAV, WORKSPACE_NAV, isResearchPath } from "@/lib/research/navigation";
import { cn } from "@/lib/utils";

function LogoMark() {
  return (
    <div className="flex h-6 w-6 items-center justify-center rounded bg-mint/15">
      <div className="flex h-3 w-3 flex-col justify-between">
        <span className="h-px w-full rounded-full bg-mint" />
        <span className="h-px w-2/3 rounded-full bg-mint/70" />
        <span className="h-px w-full rounded-full bg-mint" />
      </div>
    </div>
  );
}

interface NavbarProps {
  username: string;
}

export function Navbar({ username }: NavbarProps) {
  const pathname = usePathname();
  const research = isResearchPath(pathname);
  const sectionNav = research ? RESEARCH_NAV : PRIMARY_NAV;

  return (
    <header className="border-b border-border" data-testid="dashboard-navbar">
      <div className="flex h-12 items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-5">
          <div className="flex shrink-0 items-center gap-2">
            <LogoMark />
            <span className="text-[13px] font-semibold tracking-tight text-text-primary">
              SAVE-MONEY BOT
            </span>
          </div>

          <nav
            className="hidden items-center gap-1 rounded border border-border p-0.5 md:flex"
            data-testid="workspace-switch"
            aria-label="Workspace"
          >
            {WORKSPACE_NAV.map((item) => {
              const active =
                item.href === "/dashboard/research"
                  ? research
                  : !research &&
                    (pathname === "/dashboard" ||
                      (pathname?.startsWith("/dashboard/") === true &&
                        !isResearchPath(pathname)));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "rounded px-2.5 py-1 text-[12px] transition-colors",
                    active
                      ? "bg-mint/15 font-medium text-mint"
                      : "text-text-secondary hover:text-text-primary",
                  )}
                  data-testid={`workspace-${item.label.toLowerCase()}`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <nav className="hidden items-center gap-4 lg:flex" data-testid="section-nav">
            {sectionNav.map((item) => {
              const active =
                item.href === "/dashboard" || item.href === "/dashboard/research"
                  ? pathname === item.href
                  : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "relative flex h-12 items-center text-[13px] transition-colors",
                    active
                      ? "nav-active font-medium text-mint"
                      : "text-text-secondary hover:text-text-primary",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <div className="flex items-center gap-1.5 rounded border border-border px-1.5 py-1">
            <div className="flex h-5 w-5 items-center justify-center rounded-full bg-mint/20 text-[9px] font-medium text-mint">
              {username.slice(0, 2).toUpperCase()}
            </div>
            <span
              className="hidden text-[13px] text-text-primary sm:block"
              data-testid="session-username"
            >
              {username}
            </span>
          </div>
          <LogoutButton />
        </div>
      </div>
    </header>
  );
}
