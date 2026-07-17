import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  padding?: "none" | "xs" | "sm" | "md" | "lg";
  id?: string;
  "data-testid"?: string;
}

const paddingMap = {
  none: "",
  xs: "p-2.5",
  sm: "p-3",
  md: "p-3.5",
  lg: "p-4",
};

export function Card({
  children,
  className,
  padding = "md",
  id,
  "data-testid": dataTestId,
}: CardProps) {
  return (
    <div
      {...(id ? { id } : {})}
      {...(dataTestId ? { "data-testid": dataTestId } : {})}
      className={cn("card-surface", paddingMap[padding], className)}
    >
      {children}
    </div>
  );
}

interface PanelHeaderProps {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  compact?: boolean;
}

export function PanelHeader({
  title,
  subtitle,
  action,
  compact,
}: PanelHeaderProps) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-2",
        compact ? "mb-2" : "mb-2.5",
      )}
    >
      <div className="min-w-0">
        <h3 className="text-[13px] font-medium leading-none text-text-primary">
          {title}
        </h3>
        {subtitle && (
          <p className="mt-0.5 text-[11px] text-text-muted">{subtitle}</p>
        )}
      </div>
      {action}
    </div>
  );
}

interface BadgeProps {
  children: ReactNode;
  variant?: "mint" | "positive" | "negative" | "neutral" | "warning";
  className?: string;
}

const badgeVariants = {
  mint: "bg-mint-glow text-mint border-mint/20",
  positive: "bg-mint/10 text-positive border-mint/15",
  negative: "bg-red-500/10 text-negative border-red-500/15",
  neutral: "bg-white/5 text-text-secondary border-white/10",
  warning: "bg-amber-500/10 text-warning border-amber-500/15",
};

export function Badge({ children, variant = "neutral", className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[4px] border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.04em]",
        badgeVariants[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}

interface ToggleProps {
  enabled: boolean;
  onChange?: (enabled: boolean) => void;
  label?: string;
  small?: boolean;
  disabled?: boolean;
}

export function Toggle({
  enabled,
  onChange,
  label,
  small,
  disabled = false,
}: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-label={label}
      aria-disabled={disabled}
      disabled={disabled}
      onClick={() => {
        if (disabled) return;
        onChange?.(!enabled);
      }}
      className={cn(
        "relative shrink-0 rounded-full transition-colors",
        small ? "h-5 w-9" : "h-5 w-9",
        enabled ? "bg-mint/35" : "bg-white/10",
        disabled && "cursor-not-allowed opacity-50",
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 rounded-full transition-all",
          small ? "h-4 w-4" : "h-4 w-4",
          enabled ? "left-4 bg-mint" : "left-0.5 bg-text-muted",
        )}
      />
    </button>
  );
}

interface NumberInputProps {
  value: string;
  suffix?: string;
  className?: string;
  disabled?: boolean;
}

export function NumberInput({
  value,
  suffix,
  className,
  disabled = false,
}: NumberInputProps) {
  return (
    <div className={cn("flex items-center gap-0.5", className)}>
      <input
        type="text"
        readOnly
        disabled={disabled}
        aria-disabled={disabled}
        value={value}
        className={cn(
          "w-12 rounded-[4px] border border-border bg-bg-card-alt px-1.5 py-0.5 text-right font-mono text-[12px] text-text-primary",
          disabled && "cursor-not-allowed opacity-50",
        )}
      />
      {suffix && <span className="text-[11px] text-text-muted">{suffix}</span>}
    </div>
  );
}

interface SelectProps {
  value: string;
  options: string[];
  className?: string;
  disabled?: boolean;
}

export function Select({
  value,
  options,
  className,
  disabled = false,
}: SelectProps) {
  return (
    <select
      defaultValue={value}
      disabled={disabled}
      aria-disabled={disabled}
      className={cn(
        "w-full rounded-[6px] border border-border bg-bg-card-alt px-2 py-1 text-[12px] text-text-primary",
        disabled && "cursor-not-allowed opacity-50",
        className,
      )}
    >
      {options.map((opt) => (
        <option key={opt} value={opt}>
          {opt}
        </option>
      ))}
    </select>
  );
}

export function CoinBadge({
  coin,
  color,
  symbol,
}: {
  coin: string;
  color: string;
  symbol: string;
}) {
  return (
    <div className="flex items-center gap-1">
      <div
        className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[8px] font-semibold text-white"
        style={{ backgroundColor: color }}
      >
        {coin}
      </div>
      <span className="font-mono text-[12px] text-text-primary">{symbol}</span>
    </div>
  );
}

export function PnlPill({
  value,
  formatted,
}: {
  value: number;
  formatted: string;
}) {
  return (
    <span
      className={cn(
        "inline-block rounded-[4px] px-1.5 py-0.5 font-mono text-[11px] leading-none",
        value >= 0
          ? "bg-mint/12 text-positive"
          : "bg-negative/10 text-negative",
      )}
    >
      {formatted}
    </span>
  );
}
