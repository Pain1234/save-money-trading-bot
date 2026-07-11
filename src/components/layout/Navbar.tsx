"use client";

import { NAV_ITEMS } from "@/lib/mock-data";
import { cn } from "@/lib/utils";
import { Bell, ChevronDown, Moon, Sun } from "lucide-react";
import { useState } from "react";

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

export function Navbar() {
  const [darkMode, setDarkMode] = useState(true);

  return (
    <header className="border-b border-border">
      <div className="flex h-12 items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-5">
          <div className="flex shrink-0 items-center gap-2">
            <LogoMark />
            <span className="text-[13px] font-semibold tracking-tight text-text-primary">
              SAVE-MONEY BOT
            </span>
          </div>

          <nav className="hidden items-center gap-4 md:flex">
            {NAV_ITEMS.map((item) => (
              <a
                key={item.label}
                href={item.href}
                className={cn(
                  "relative flex h-12 items-center text-[13px] transition-colors",
                  item.active
                    ? "nav-active font-medium text-mint"
                    : "text-text-secondary hover:text-text-primary",
                )}
              >
                {item.label}
              </a>
            ))}
          </nav>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            aria-label="Theme umschalten"
            onClick={() => setDarkMode(!darkMode)}
            className="flex h-7 w-7 items-center justify-center rounded text-text-secondary hover:bg-white/5 hover:text-text-primary"
          >
            {darkMode ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
          </button>
          <button
            type="button"
            aria-label="Benachrichtigungen"
            className="flex h-7 w-7 items-center justify-center rounded text-text-secondary hover:bg-white/5 hover:text-text-primary"
          >
            <Bell className="h-3.5 w-3.5" />
          </button>

          <button
            type="button"
            className="ml-0.5 flex items-center gap-1.5 rounded border border-border px-1.5 py-1 hover:bg-white/5"
          >
            <div className="flex h-5 w-5 items-center justify-center rounded-full bg-mint/20 text-[9px] font-medium text-mint">
              MM
            </div>
            <span className="hidden text-[13px] text-text-primary sm:block">
              Max Mustermann
            </span>
            <ChevronDown className="h-3 w-3 text-text-muted" />
          </button>
        </div>
      </div>
    </header>
  );
}
