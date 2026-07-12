import { ErrorPanel } from "@/components/monitor/ErrorPanel";
import { fetchWallet, getMonitoringErrorMessage } from "@/lib/paper-api/client";
export default async function WalletPage() {
  try {
    const wallet = await fetchWallet();
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">Paper Wallet</h1>
        <dl className="grid gap-3 md:grid-cols-2">
          {Object.entries(wallet).map(([key, value]) => (
            <div key={key} className="rounded-xl border border-border-subtle bg-bg-elevated p-4">
              <dt className="text-xs uppercase text-text-muted">{key}</dt>
              <dd className="mt-1 text-lg">{String(value)}</dd>
            </div>
          ))}
        </dl>
      </div>
    );
  } catch (error) {
    return (
      <ErrorPanel
        title="Wallet unavailable"
        message={getMonitoringErrorMessage(error)}
      />
    );
  }}
