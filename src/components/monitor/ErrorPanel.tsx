export function ErrorPanel({
  title,
  message,
}: {
  title: string;
  message?: string;
}) {
  return (
    <div
      data-testid="dashboard-error-panel"
      className="rounded-xl border border-red-500/40 bg-red-500/10 p-6"
    >
      <h1 className="text-xl font-semibold text-red-300">{title}</h1>
      <p className="mt-2 text-sm text-text-muted">
        {message ??
          "The private monitoring API is unreachable or returned an error. This page does not use cached or mock data."}
      </p>
    </div>
  );
}
