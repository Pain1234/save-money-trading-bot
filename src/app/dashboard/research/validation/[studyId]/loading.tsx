import { ResearchLoadingSkeleton } from "@/components/research/chrome/ResearchPageChrome";

export default function ResearchValidationDetailLoading() {
  return <ResearchLoadingSkeleton testId="validation-detail-page-loading" rows={2} />;
}
