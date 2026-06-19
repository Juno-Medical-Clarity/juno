import { describe, expect, it } from 'vitest';
import { versionPath } from './router';

describe('versionPath', () => {
  it('routes known versions through the single simplify page bridge', () => {
    expect(versionPath('v1')).toBe('/?version=v1');
    expect(versionPath('v1-1')).toBe('/?version=v1-1');
    expect(versionPath('v1-2')).toBe('/?version=v1-2');
  });

  it('falls back to the single simplify page for unknown versions', () => {
    expect(versionPath('unknown')).toBe('/');
  });
});
