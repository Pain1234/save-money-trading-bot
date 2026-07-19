"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { RESEARCH_NAV, isResearchNavActive } from "@/lib/research/navigation";
import { cn } from "@/lib/utils";

export function ResearchSidebar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!mobileOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMobileOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  function renderNav(testIdPrefix: string) {
    return (
      <nav className="flex flex-col gap-0.5" aria-label="Research">
        {RESEARCH_NAV.map((item) => {
          const active = isResearchNavActive(pathname, item.href);
          const slug = item.label.toLowerCase().replace(/\s+/g, "-");
          return (
            <Link
              key={`${testIdPrefix}-${item.href}`}
              href={item.href}
              onClick={() => setMobileOpen(false)}
              className={cn(
                "rounded-sm px-2 py-1.5 text-[12px] transition-colors",
                active
                  ? "bg-mint/10 font-medium text-mint"
                  : "text-text-secondary hover:bg-white/5 hover:text-text-primary",
              )}
              aria-current={active ? "page" : undefined}
              data-testid={`${testIdPrefix}-${slug}`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    );
  }

  return (
    <>
      <div className="border-b border-border px-[var(--rs-shell-x)] py-2 lg:hidden">
        <button
          type="button"
          className="rounded-sm border border-border px-2.5 py-1 text-[11px] text-text-secondary hover:text-text-primary"
          aria-expanded={mobileOpen}
          aria-controls="research-sidebar-nav"
          data-testid="research-nav-toggle"
          onClick={() => setMobileOpen((open) => !open)}
        >
          {mobileOpen ? "Navigation schließen" : "Research-Navigation"}
        </button>
        {mobileOpen ? (
          <div
            id="research-sidebar-nav"
            className="mt-2"
            role="dialog"
            aria-label="Research navigation"
          >
            {renderNav("research-nav-mobile")}
          </div>
        ) : null}
      </div>

      <aside
        className="hidden min-h-full w-[var(--rs-sidebar-width)] shrink-0 self-stretch border-r border-border bg-bg-base lg:block"
        data-testid="research-sidebar"
        aria-label="Research sidebar"
      >
        <div className="sticky top-0 space-y-3 px-3 py-3">
          <div>
            <h1 className="text-[15px] font-semibold leading-tight tracking-tight text-text-primary">
              Research Workspace
            </h1>
            <p className="mt-1 text-[11px] leading-relaxed text-text-muted">
              Registry, Lab, Gates und Validation — read-only Evidence. Keine
              Promotion, keine Live-Orders.
            </p>
          </div>
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-[0.06em] text-text-muted">
              Research
            </p>
            {renderNav("research-nav")}
          </div>
        </div>
      </aside>
    </>
  );
}
