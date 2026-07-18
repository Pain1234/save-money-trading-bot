import { ResearchSidebar } from "@/components/research/shell/ResearchSidebar";
import { ResearchTicker } from "@/components/research/shell/ResearchTicker";
import { ResearchTopbar } from "@/components/research/shell/ResearchTopbar";

interface ResearchShellProps {
  username: string;
  children: React.ReactNode;
}

/** Full-width Hyperliquid-style Research chrome (#298). Monitor chrome is separate. */
export function ResearchShell({ username, children }: ResearchShellProps) {
  return (
    <div
      className="research-shell flex min-h-screen flex-col bg-bg-base text-text-primary"
      data-testid="research-shell"
    >
      <ResearchTopbar username={username} />
      <ResearchTicker />
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <ResearchSidebar />
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <main className="min-w-0 flex-1 px-[var(--rs-shell-x)] py-[var(--rs-shell-y)]">
            {children}
          </main>
          <footer
            className="mt-auto border-t border-border px-[var(--rs-shell-x)] py-2"
            data-testid="research-footer"
            role="contentinfo"
          >
            <p className="text-[10px] leading-relaxed text-text-muted">
              Research Workspace — Evidence aus Registry/API. Keine Anlageberatung.
              Keine Live-Orders, keine Wallet-Signatur, keine Promotion.
            </p>
          </footer>
        </div>
      </div>
    </div>
  );
}
