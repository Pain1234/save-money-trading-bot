import { ResearchLoadingSkeleton } from "@/components/research/chrome/ResearchPageChrome";

export default function ResearchValidationLoading() {
  return <ResearchLoadingSkeleton testId="validation-page-loading" rows={2} />;
}
