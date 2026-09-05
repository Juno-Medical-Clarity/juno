import { describe, it, expect } from 'vitest';
import { buildPdfHtml, escapeHtml } from '@main/utils/buildPdfHtml';
import type { SimplifiedCarePlan } from '@main/types/envelope';

describe('alias smoke: @main/utils/buildPdfHtml', () => {
  it('produces non-empty, well-formed HTML from a minimal fixture', () => {
    const fixture: SimplifiedCarePlan = {
      doc_type: 'care_plan',
      urgency: 'normal',
      version: '1.2',
      summary: 'Take it easy for a week.',
      reason_for_visit: [],
      diagnosis: { details: [] },
      medications: [],
      tests: [],
      procedures: [],
      other: [],
      follow_up: [],
      warning_signs: [],
      questions: [],
      low_priority: [],
    };
    const html = buildPdfHtml(fixture);
    expect(html.length).toBeGreaterThan(0);
    expect(html).toContain('<!DOCTYPE html>');
    expect(html).toContain('Take it easy for a week.');
  });

  it('escapeHtml escapes the five reserved characters', () => {
    expect(escapeHtml(`<a href="x">&'</a>`)).toBe(
      '&lt;a href=&quot;x&quot;&gt;&amp;&#039;&lt;/a&gt;',
    );
  });
});
