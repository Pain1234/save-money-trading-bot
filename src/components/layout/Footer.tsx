import { AlertTriangle } from "lucide-react";

export function Footer() {
  return (
    <footer className="page-footer border-t border-border" data-testid="dashboard-footer">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-1.5">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-text-muted" />
          <p className="text-[11px] leading-relaxed text-text-muted">
            Disclaimer: Krypto-Perpetual-Trading birgt erhebliche Risiken. Keine
            Anlageberatung. Dieses Dashboard ist ausschließlich read-only
            Paper-Trading-Monitoring — keine Live-Orders, keine Wallet-Signatur.
          </p>
        </div>
        <p className="shrink-0 whitespace-nowrap text-[11px] text-text-muted">
          Marktdaten-Bezug:{" "}
          <span className="text-text-secondary">Hyperliquid (Paper)</span>
        </p>
      </div>
    </footer>
  );
}
