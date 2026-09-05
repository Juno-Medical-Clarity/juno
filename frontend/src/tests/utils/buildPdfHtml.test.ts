import { describe, it, expect } from 'vitest';
import { buildPdfHtml, escapeHtml } from '../../utils/buildPdfHtml';
import type { SimplifiedCarePlan } from '../../types/envelope';

function makeMinimalPlan(overrides: Partial<SimplifiedCarePlan> = {}): SimplifiedCarePlan {
  return {
    doc_type: 'care_plan',
    urgency: 'normal',
    version: '1.2',
    summary: '',
    reason_for_visit: [],
    diagnosis: { main_conclusion: undefined, changed_since_last_visit: undefined, details: [] },
    medications: [],
    tests: [],
    procedures: [],
    other: [],
    follow_up: [],
    warning_signs: [],
    questions: [],
    low_priority: [],
    ...overrides,
  };
}

describe('escapeHtml', () => {
  it('escapes ampersand', () => {
    expect(escapeHtml('a & b')).toBe('a &amp; b');
  });

  it('escapes < and >', () => {
    expect(escapeHtml('<b>hi</b>')).toBe('&lt;b&gt;hi&lt;/b&gt;');
  });

  it('escapes double quotes', () => {
    expect(escapeHtml('"quoted"')).toBe('&quot;quoted&quot;');
  });

  it('escapes single quotes', () => {
    expect(escapeHtml("it's")).toBe("it&#039;s");
  });

  it('returns plain text unchanged', () => {
    expect(escapeHtml('hello world')).toBe('hello world');
  });
});

describe('buildPdfHtml', () => {
  it('returns a complete HTML document', () => {
    const html = buildPdfHtml(makeMinimalPlan());
    expect(html).toContain('<!DOCTYPE html>');
    expect(html).toContain('<html>');
    expect(html).toContain('</html>');
    expect(html).toContain('Your Care Plan');
  });

  it('includes summary section when summary is provided', () => {
    const html = buildPdfHtml(makeMinimalPlan({ summary: 'You are doing well.' }));
    expect(html).toContain('What You Need to Know');
    expect(html).toContain('You are doing well.');
  });

  it('does not include summary section when summary is empty', () => {
    const html = buildPdfHtml(makeMinimalPlan({ summary: '' }));
    expect(html).not.toContain('What You Need to Know');
  });

  it('includes reason_for_visit section', () => {
    const html = buildPdfHtml(makeMinimalPlan({
      reason_for_visit: [{ reason: 'Chest pain', description: 'Sharp pain on left side' }],
    }));
    expect(html).toContain('Why You Came In');
    expect(html).toContain('Chest pain');
    expect(html).toContain('Sharp pain on left side');
  });

  it('includes medications section with details', () => {
    const html = buildPdfHtml(makeMinimalPlan({
      medications: [{
        title: 'Metformin',
        plain_name: 'Blood sugar medication',
        why: 'To manage diabetes',
        dosage: '500mg',
        frequency: 'twice daily',
        importance: 'high',
      }],
    }));
    expect(html).toContain('Your Medications');
    expect(html).toContain('Metformin');
    expect(html).toContain('Blood sugar medication');
  });

  it('includes questions section', () => {
    const html = buildPdfHtml(makeMinimalPlan({
      questions: ['When should I return?', 'What are the side effects?'],
    }));
    expect(html).toContain('Questions to Ask');
    expect(html).toContain('When should I return?');
  });

  it('includes follow-up section', () => {
    const html = buildPdfHtml(makeMinimalPlan({
      follow_up: [{ description: 'See cardiologist', time_frame: 'In 2 weeks' }],
    }));
    expect(html).toContain('Follow-Up');
    expect(html).toContain('See cardiologist');
    expect(html).toContain('In 2 weeks');
  });

  it('escapes user content in the output', () => {
    const html = buildPdfHtml(makeMinimalPlan({
      summary: '<script>alert("xss")</script>',
    }));
    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
  });

  it('warning_signs are sorted by urgency (emergency first)', () => {
    const html = buildPdfHtml(makeMinimalPlan({
      warning_signs: [
        { symptom: 'Swelling', what_to_do: 'Monitor', urgency: 'monitor', importance: 'low' },
        { symptom: 'Chest pain', what_to_do: 'Call 911', urgency: 'emergency', importance: 'high' },
      ],
    }));
    const emergencyIdx = html.indexOf('Chest pain');
    const monitorIdx = html.indexOf('Swelling');
    expect(emergencyIdx).toBeLessThan(monitorIdx);
  });

  it('escapes markup in a test\'s preparation field (stored XSS regression)', () => {
    const html = buildPdfHtml(makeMinimalPlan({
      tests: [{
        title: 'Blood test',
        description: 'Checks blood sugar',
        preparation: '<img src=x onerror=alert(1)>Fast for 8 hours',
        importance: 'high',
      }],
    }));
    expect(html).not.toContain('<img src=x onerror=alert(1)>');
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;Fast for 8 hours');
  });

  it('includes glossary section when terms are provided', () => {
    const html = buildPdfHtml(makeMinimalPlan({
      terms: { hypertension: { definition: 'High blood pressure', source: 'medical', imgUrl: null, altText: null } },
    }));
    expect(html).toContain('Medical Terms Glossary');
    expect(html).toContain('hypertension');
    expect(html).toContain('High blood pressure');
  });
});
