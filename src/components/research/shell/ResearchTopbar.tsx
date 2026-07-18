"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { LogoutButton } from "@/components/monitor/LogoutButton";
import { WORKSPACE_NAV, isResearchPath } from "@/lib/research/navigation";
import { cn } from "@/lib/utils";

function LogoMark() {
  return (
    <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-sm bg-mint/15">
      <div className="flex h-2.5 w-2.5 flex-col justify-between">
        <span className="h-px w-full rounded-full bg-mint" />
        <span className="h-px w-2/3 rounded-full bg-mint/70" />
        <span className="h-px w-full rounded-full bg-mint" />
      </div>
    </div>
  );
}

interface ResearchTopbarProps {
  username: string;
}

export function ResearchTopbar({ username }: ResearchTopbarProps) {
  const pathname = usePathname();
  const research = isResearchPath(pathname);
  const initials = username.slice(0, 2).toUpperCase();

  return (
    <header
      className="border-b border-border"
      data-testid="research-topbar"
      role="banner"
    >
      <div className="flex h-11 items-center justify-between gap-2 px-[var(--rs-shell-x)]">
        <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
          <div className="flex min-w-0 shrink-0 items-center gap-1.5">
            <LogoMark />
            <span className="hidden text-[12px] font-semibold tracking-tight text-text-primary sm:inline">
              SAVE-MONEY BOT
            </span>
            <span className="sr-only sm:hidden">SAVE-MONEY BOT</span>
          </div>

          <nav
            className="flex min-w-0 shrink items-center gap-0.5 rounded-sm border border-border p-0.5"
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
              const short =
                item.label === "Monitor"
                  ? "Mon"
                  : item.label === "Research"
                    ? "Res"
                    : item.label;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "rounded-sm px-1.5 py-1 text-[11px] transition-colors sm:px-2.5",
                    active
                      ? "bg-mint/15 font-medium text-mint"
                      : "text-text-secondary hover:text-text-primary",
                  )}
                  data-testid={`workspace-${item.label.toLowerCase()}`}
                  aria-current={active ? "page" : undefined}
                  title={item.label}
                >
                  <span className="sm:hidden">{short}</span>
                  <span className="hidden sm:inline">{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          <div
            className="flex items-center gap-1.5 rounded-sm border border-border px-1.5 py-1"
            title={username}
          >
            <div
              className="flex h-5 w-5 items-center justify-center rounded-full bg-mint/20 text-[9px] font-medium text-mint"
              aria-hidden="true"
            >
              {initials}
            </div>
            <span
              className="hidden max-w-[7rem] truncate text-[12px] text-text-primary md:inline"
              data-testid="session-username"
            >
              {username}
            </span>
            <span className="sr-only">{username}</span>
          </div>
          <LogoutButton className="rounded-sm px-2 py-1 text-[11px]" />
        </div>
      </div>
    </header>
  );
}
