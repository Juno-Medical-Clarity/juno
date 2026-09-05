import { describe, it, expect } from 'vitest';
import { validateFiles, validateText, MAX_FILES, MAX_TEXT_LENGTH } from '../../utils/validateFiles';

function fakeFile(name: string, sizeBytes: number): File {
  const file = new File([''], name);
  Object.defineProperty(file, 'size', { value: sizeBytes });
  return file;
}

describe('validateFiles', () => {
  it('accepts a valid mixed selection under all four caps', () => {
    expect(validateFiles([fakeFile('a.pdf', 1000), fakeFile('b.png', 2000)])).toBeNull();
  });

  it('returns null for an empty selection', () => {
    expect(validateFiles([])).toBeNull();
  });

  it('rejects more than MAX_FILES with the exact count', () => {
    const files = Array.from({ length: MAX_FILES + 1 }, (_, i) => fakeFile(`f${i}.pdf`, 100));
    const err = validateFiles(files);
    expect(err).toContain(`up to ${MAX_FILES} files`);
    expect(err).toContain(`selected ${MAX_FILES + 1}`);
  });

  it('rejects a disallowed extension, listing the filename', () => {
    const err = validateFiles([fakeFile('animated.gif', 100)]);
    expect(err).toContain('animated.gif');
  });

  it('rejects a single file over 10MB', () => {
    const err = validateFiles([fakeFile('big.pdf', 11 * 1024 * 1024)]);
    expect(err).toContain('big.pdf');
    expect(err).toContain('10MB');
  });

  it('rejects a valid-individually-sized set whose total exceeds 25MB', () => {
    const files = [fakeFile('a.pdf', 9 * 1024 * 1024), fakeFile('b.pdf', 9 * 1024 * 1024), fakeFile('c.pdf', 9 * 1024 * 1024)];
    const err = validateFiles(files);
    expect(err).toContain('25MB total');
  });
});

describe('validateText', () => {
  it('accepts text at or under the cap', () => {
    expect(validateText('a'.repeat(MAX_TEXT_LENGTH))).toBeNull();
  });

  it('rejects text over the cap with the exact length in the message', () => {
    const text = 'a'.repeat(MAX_TEXT_LENGTH + 1);
    const err = validateText(text);
    expect(err).toContain(`${MAX_TEXT_LENGTH + 1}`.replace(/\B(?=(\d{3})+(?!\d))/g, ','));
  });
});
