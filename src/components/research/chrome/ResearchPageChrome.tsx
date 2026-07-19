import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Shared dense Research route tokens (#301) — keep Monitor Card untouched. */
export const rs = {
  page: "space-y-3",
  h1: "text-[18px] font-semibold tracking-tight text-text-primary",
  lead: "mt-1 max-w-3xl text-[12px] leading-relaxed text-text-secondary",
  sectionTitle: "mb-2 text-[12px] font-semibold text-text-primary",
  label: "text-[11px] uppercase tracking-wide text-text-muted",
  mono: "font-mono text-[12px] text-text-primary",
  muted: "text-[12px] text-text-muted",
  btnPrimary:
    "rounded-sm bg-mint/20 px-2.5 py-1 text-[12px] text-mint hover:bg-mint/25",
  btnSecondary:
    "rounded-sm border border-border px-2.5 py-1 text-[12px] text-text-secondary hover:text-text-primary",
  input:
    "rounded-sm border border-border bg-bg-elevated px-2.5 py-1 text-[12px] text-text-primary",
  select:
    "rounded-sm border border-border bg-bg-elevated px-2 py-1 text-[12px] text-text-primary",
  tableWrap: "overflow-x-auto rounded-sm border border-border-subtle",
  table: "min-w-full text-left text-[12px]",
  th: "px-2 py-1 font-medium text-text-muted",
  td: "px-2 py-1.5",
  backLink: "text-[11px] text-text-muted hover:text-mint",
} as const;

interface ResearchPageHeaderProps {
  title: string;
  description?: string;
  backHref?: string;
  backLabel?: string;
  titleMono?: boolean;
  actions?: ReactNode;
  testId?: string;
}

/** Dense page header matching Overview / ResearchShell typography. */
export function ResearchPageHeader({
  title,
  description,
  backHref,
  backLabel,
  titleMono = false,
  actions,
  testId,
}: ResearchPageHeaderProps) {
  return (
    <div
      className="flex flex-wrap items-end justify-between gap-3"
      data-testid={testId}
    >
      <div className="min-w-0">
        {backHref ? (
          <Link href={backHref} className={rs.backLink}>
            {backLabel ?? "← Zurück"}
          </Link>
        ) : null}
        <h1
          className={cn(
            rs.h1,
            backHref && "mt-1",
            titleMono && "font-mono text-[16px]",
          )}
        >
          {title}
        </h1>
        {description ? <p className={rs.lead}>{description}</p> : null}
      </div>
      {actions ? (
        <div className="flex flex-wrap gap-2">{actions}</div>
      ) : null}
    </div>
  );
}

interface ResearchApiErrorProps {
  message: string;
  testId?: string;
  title?: string;
}

/** Fail-closed Research API error — dense, no invented metrics. */
export function ResearchApiError({
  message,
  testId = "research-api-error",
  title = "Research API Error",
}: ResearchApiErrorProps) {
  return (
    <div
      data-testid={testId}
      className="rounded-sm border border-red-500/40 bg-red-500/10 px-3 py-3"
      role="alert"
    >
      <h1 className="text-[16px] font-semibold text-red-300">{title}</h1>
      <p className="mt-1 text-[12px] text-red-200/90">{message}</p>
    </div>
  );
}

interface ResearchEmptyProps {
  title?: string;
  message: string;
  testId?: string;
  actions?: ReactNode;
}

export function ResearchEmpty({
  title,
  message,
  testId,
  actions,
}: ResearchEmptyProps) {
  return (
    <div data-testid={testId} className={rs.page}>
      {title ? <h1 className={rs.h1}>{title}</h1> : null}
      <p className={rs.muted}>{message}</p>
      {actions}
    </div>
  );
}

interface ResearchLoadingSkeletonProps {
  rows?: number;
  testId?: string;
}

/** Compact pulse skeleton for research route loading.tsx files. */
export function ResearchLoadingSkeleton({
  rows = 2,
  testId = "research-loading",
}: ResearchLoadingSkeletonProps) {
  return (
    <div className={rs.page} data-testid={testId} aria-busy="true">
      <div className="h-8 w-48 animate-pulse rounded-sm bg-white/5" />
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          className="h-24 w-full animate-pulse rounded-sm bg-white/5"
        />
      ))}
    </div>
  );
}

interface ResearchTableFrameProps {
  children: ReactNode;
  className?: string;
  testId?: string;
}

export function ResearchTableFrame({
  children,
  className,
  testId,
}: ResearchTableFrameProps) {
  return (
    <div
      className={cn(rs.tableWrap, className)}
      data-testid={testId}
    >
      {children}
    </div>
  );
}

interface ResearchNotFoundProps {
  title: string;
  message?: string;
  backHref: string;
  backLabel: string;
}

export function ResearchNotFound({
  title,
  message = "Die angeforderte Resource wurde nicht gefunden.",
  backHref,
  backLabel,
}: ResearchNotFoundProps) {
  return (
    <div className={rs.page}>
      <h1 className={rs.h1}>{title}</h1>
      <p className={rs.muted}>{message}</p>
      <Link href={backHref} className={rs.btnSecondary}>
        {backLabel}
      </Link>
    </div>
  );
}
