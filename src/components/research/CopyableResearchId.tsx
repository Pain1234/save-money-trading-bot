"use client";

import { useState } from "react";
import Link from "next/link";

import {
  researchIdAriaLabel,
  shortenResearchId,
} from "@/lib/research/research-id";
import { cn } from "@/lib/utils";

interface CopyableResearchIdProps {
  id: string;
  kind: string;
  href?: string | null;
  className?: string;
  monoClassName?: string;
}

/** Short display + full aria-label/title + Copy (full ID). Overview only. */
export function CopyableResearchId({
  id,
  kind,
  href = null,
  className,
  monoClassName,
}: CopyableResearchIdProps) {
  const [copied, setCopied] = useState(false);
  const short = shortenResearchId(id);
  const label = researchIdAriaLabel(kind, id);

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(id);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  const idNode = href ? (
    <Link
      href={href}
      className={cn("font-mono text-mint hover:underline", monoClassName)}
      title={id}
      aria-label={label}
    >
      {short}
    </Link>
  ) : (
    <span
      className={cn("font-mono text-text-secondary", monoClassName)}
      title={id}
      aria-label={label}
    >
      {short}
    </span>
  );

  return (
    <span
      className={cn("inline-flex max-w-full items-center gap-1", className)}
      data-testid={`copyable-id-${kind}`}
    >
      {idNode}
      <button
        type="button"
        onClick={onCopy}
        className="shrink-0 rounded-sm border border-border px-1 py-0.5 text-[11px] text-text-secondary hover:text-text-primary"
        aria-label={`Copy ${kind} ${id}`}
        data-testid={`copy-id-${kind}`}
        data-full-id={id}
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </span>
  );
}
