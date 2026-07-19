import { rs } from "@/components/research/chrome/ResearchPageChrome";

export default function ResearchOverviewLoading() {
  return (
    <div
      data-testid="research-overview-loading"
      className={rs.page}
      aria-busy="true"
    >
      <div className="h-8 w-48 animate-pulse rounded-sm bg-white/5" />
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-20 animate-pulse rounded-sm bg-white/5" />
        ))}
      </div>
    </div>
  );
}
