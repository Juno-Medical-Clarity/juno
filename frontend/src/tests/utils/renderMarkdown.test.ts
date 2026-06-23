import { describe, it, expect } from 'vitest';
import { renderMarkdown } from '../../utils/renderMarkdown';
import smogContent from '../../docs/grading/smog.md?raw';

describe('renderMarkdown', () => {
  it('converts # heading to <h1>', () => {
    expect(renderMarkdown('# Hello')).toContain('<h1>Hello</h1>');
  });

  it('converts ## heading to <h2>', () => {
    expect(renderMarkdown('## Section')).toContain('<h2>Section</h2>');
  });

  it('converts **bold** to <strong>', () => {
    expect(renderMarkdown('**bold**')).toContain('<strong>bold</strong>');
  });

  it('converts [text](url) to <a> with target and rel', () => {
    const result = renderMarkdown('[click](http://example.com)');
    expect(result).toContain('<a href="http://example.com"');
    expect(result).toContain('target="_blank"');
    expect(result).toContain('rel="noopener noreferrer"');
    expect(result).toContain('>click</a>');
  });

  it('converts - item to <li> wrapped in <ul>', () => {
    const result = renderMarkdown('- item one\n- item two');
    expect(result).toContain('<ul>');
    expect(result).toContain('<li>item one</li>');
    expect(result).toContain('<li>item two</li>');
  });

  it('does not crash on empty string', () => {
    expect(() => renderMarkdown('')).not.toThrow();
  });

  it('smoke test: renders smog.md without crashing and without raw markdown', () => {
    const result = renderMarkdown(smogContent);
    expect(result).not.toContain('# SMOG');   // h1 should be converted
    expect(result).toContain('<h1>');
    expect(result).not.toMatch(/^\*\*/m);       // no raw bold at line start
  });
});
