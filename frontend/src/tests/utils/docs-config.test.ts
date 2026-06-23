import { describe, it, expect } from 'vitest';
import { DOCS_SECTIONS } from '../../docs-config';

describe('DOCS_SECTIONS', () => {
  it('has at least one section', () => {
    expect(DOCS_SECTIONS.length).toBeGreaterThan(0);
  });

  it('each section has at least one entry', () => {
    DOCS_SECTIONS.forEach(section => {
      expect(section.entries.length).toBeGreaterThan(0);
    });
  });

  it('grading section has all expected slugs', () => {
    const grading = DOCS_SECTIONS.find(s => s.id === 'grading');
    expect(grading).toBeDefined();
    const slugs = grading!.entries.map(e => e.slug);
    expect(slugs).toEqual(['combined-scoring', 'smog', 'flesch-kincaid', 'dale-chall', 'pemat', 'sam', 'cdc-cci']);
  });

  it('all grading entries have non-empty slug, name, and content', () => {
    const grading = DOCS_SECTIONS.find(s => s.id === 'grading')!;
    grading.entries.forEach(e => {
      expect(e.slug).toBeTruthy();
      expect(e.name).toBeTruthy();
      expect(e.content).toBeTruthy();
      expect(e.content.length).toBeGreaterThan(10);
    });
  });

  it('all slugs within grading section are unique', () => {
    const grading = DOCS_SECTIONS.find(s => s.id === 'grading')!;
    const slugs = grading.entries.map(e => e.slug);
    const unique = new Set(slugs);
    expect(unique.size).toBe(slugs.length);
  });
});
