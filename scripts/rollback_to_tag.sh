#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/rollback_to_tag.sh <prod-tag>

Triggers the Rollback Production GitHub Actions workflow for <prod-tag>.
The workflow checks out the tag and redeploys backend + frontend from that
tag without changing main or deploy.

Example:
  scripts/rollback_to_tag.sh prod-20260619-023500
USAGE
}

tag_name="${1:-}"
if [[ -z "$tag_name" || "$tag_name" == "-h" || "$tag_name" == "--help" ]]; then
  usage
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required to trigger the rollback workflow." >&2
  exit 1
fi

remote="${REMOTE:-origin}"
workflow="${ROLLBACK_WORKFLOW:-rollback-production.yml}"

git fetch "$remote" --tags
if ! git rev-parse --verify --quiet "refs/tags/$tag_name" >/dev/null; then
  echo "Tag not found: $tag_name" >&2
  exit 1
fi

gh workflow run "$workflow" -f "prod_tag=$tag_name"
echo "Triggered $workflow for $tag_name"
