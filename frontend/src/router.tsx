import { VERSIONS } from './config';
import type { SimplifyOutput } from './types/envelope';

export interface VersionRouteState {
  output?: SimplifyOutput;
}

export function versionPath(versionId: string): string {
  if (!VERSIONS.some(version => version.id === versionId)) return '/';
  return `/?version=${encodeURIComponent(versionId)}`;
}
