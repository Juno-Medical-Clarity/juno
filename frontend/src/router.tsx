import { VERSIONS } from './config';

export function versionPath(versionId: string): string {
  return VERSIONS.find(version => version.id === versionId)?.path ?? '/v1';
}
