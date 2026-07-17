export default function ResearchOverviewLoading() {
  return (
    <div data-testid="research-overview-loading" className="space-y-3">
      <div className="h-7 w-48 animate-pulse rounded bg-white/5" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-20 animate-pulse rounded-xl bg-white/5" />
        ))}
      </div>
    </div>
  );
}
