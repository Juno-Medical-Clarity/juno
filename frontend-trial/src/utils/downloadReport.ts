import { buildPdfHtml } from '@main/utils/buildPdfHtml';
import type { SimplifiedCarePlan, Grading } from '@main/types/envelope';
import { trackEvent } from '../analytics/ga';

export function downloadReport(carePlan: SimplifiedCarePlan, grading: Grading): void {
  trackEvent({ name: 'report_downloaded', params: {} });
  const html = buildPdfHtml(carePlan, grading);
  const printWindow = window.open('', '_blank');
  if (!printWindow) {
    alert('Pop-up blocked. Please allow pop-ups to download the report.');
    return;
  }
  printWindow.document.write(html);
  printWindow.document.close();
  setTimeout(() => printWindow.print(), 500);
}
