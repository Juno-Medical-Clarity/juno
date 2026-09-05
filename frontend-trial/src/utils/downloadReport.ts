import { buildPdfHtml } from '@main/utils/buildPdfHtml';
import type { SimplifiedCarePlan, Grading } from '@main/types/envelope';
import { trackEvent } from '../analytics/ga';

export function downloadReport(carePlan: SimplifiedCarePlan, grading: Grading): void {
  trackEvent({ name: 'report_downloaded', params: {} });
  const html = buildPdfHtml(carePlan, grading, {
    includeGlossary: false,
    includeReadability: false,
    includeLowPriority: false,
  });
  const printWindow = window.open('', '_blank');
  if (!printWindow) {
    alert('Pop-up blocked. Please allow pop-ups to download the report.');
    return;
  }
  // Defense-in-depth: printWindow keeps a `window.opener` handle back into this
  // tab even though we can't pass the 'noopener' feature (that would make
  // window.open return null, and we need the handle for document.write).
  // Null it out so injected markup in `html` can't reach back into this tab's
  // storage/auth via window.opener.
  printWindow.opener = null;
  printWindow.document.write(html);
  printWindow.document.close();
  setTimeout(() => printWindow.print(), 500);
}
