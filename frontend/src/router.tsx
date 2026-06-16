import { VERSIONS } from './config';
import type { SimplifyOutput } from './types/envelope';

export interface VersionRouteState {
  output?: SimplifyOutput;
}

export function versionPath(versionId: string): string {
  return VERSIONS.find(version => version.id === versionId)?.path ?? '/v1';
}
