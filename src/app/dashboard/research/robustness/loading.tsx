export default function ResearchRobustnessLoading() {
  return (
    <div data-testid="robustness-page-loading" className="space-y-3">
      <div className="h-7 w-40 animate-pulse rounded bg-white/5" />
      <div className="h-32 w-full animate-pulse rounded-xl bg-white/5" />
      <div className="h-48 w-full animate-pulse rounded-xl bg-white/5" />
    </div>
  );
}
