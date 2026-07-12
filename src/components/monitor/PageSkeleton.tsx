export function OverviewSkeleton() {
  return (
    <div className="animate-pulse space-y-6">
      <div className="flex items-center gap-3">
        <div className="h-8 w-40 rounded bg-bg-elevated" />
        <div className="h-6 w-20 rounded-full bg-bg-elevated" />
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <div
            key={index}
            className="h-24 rounded-xl border border-border-subtle bg-bg-elevated"
          />
        ))}
      </div>
    </div>
  );
}

export function DetailSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="flex items-center gap-3">
        <div className="h-8 w-56 rounded bg-bg-elevated" />
        <div className="h-6 w-20 rounded-full bg-bg-elevated" />
      </div>
      <div className="h-72 rounded-xl border border-border-subtle bg-bg-elevated" />
    </div>
  );
}

export function TableSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-8 w-48 rounded bg-bg-elevated" />
      <div className="overflow-hidden rounded-xl border border-border-subtle">
        <div className="h-10 border-b border-border-subtle bg-bg-elevated" />
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="h-12 border-b border-border-subtle bg-bg-base/40" />
        ))}
      </div>
    </div>
  );
}

export function WalletSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-8 w-32 rounded bg-bg-elevated" />
      <div className="grid gap-4 md:grid-cols-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <div
            key={index}
            className="h-20 rounded-xl border border-border-subtle bg-bg-elevated"
          />
        ))}
      </div>
    </div>
  );
}
