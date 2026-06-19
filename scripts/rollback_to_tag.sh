#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/rollback_to_tag.sh <prod-tag>

Creates a rollback branch from origin/deploy, replaces its tracked files with
the exact tree from <prod-tag>, commits the rollback, pushes the branch, and
opens a draft PR back to deploy.

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
  echo "gh CLI is required to open the rollback PR." >&2
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Working tree has uncommitted changes. Commit or stash them before rollback." >&2
  exit 1
fi

remote="${REMOTE:-origin}"
base_branch="${BASE_BRANCH:-deploy}"
safe_tag=$(sed 's/[^A-Za-z0-9._-]/-/g' <<<"$tag_name")
rollback_branch="rollback/${safe_tag}-$(date -u +%Y%m%d%H%M%S)"

git fetch "$remote" "$base_branch" --tags

if ! git rev-parse --verify --quiet "refs/tags/$tag_name" >/dev/null; then
  echo "Tag not found: $tag_name" >&2
  exit 1
fi

git switch -c "$rollback_branch" "$remote/$base_branch"

tracked_files=$(mktemp)
trap 'rm -f "$tracked_files"' EXIT
git ls-tree -r --name-only HEAD > "$tracked_files"
if [[ -s "$tracked_files" ]]; then
  xargs -r git rm -q --ignore-unmatch < "$tracked_files"
fi

git checkout "$tag_name" -- .
git add -A

if git diff --cached --quiet; then
  echo "No rollback changes needed. deploy already matches $tag_name."
  exit 0
fi

git commit -m "Rollback deploy to $tag_name"
git push -u "$remote" "$rollback_branch"

pr_body=$(mktemp)
trap 'rm -f "$tracked_files" "$pr_body"' EXIT
cat > "$pr_body" <<EOF
## Summary

Rollback deploy branch to production tag \`$tag_name\`.

## Notes

This PR replaces the tracked deploy branch files with the exact tree from \`$tag_name\`. Merging it will trigger the normal deploy workflows using that tagged code state.
EOF

gh pr create \
  --draft \
  --base "$base_branch" \
  --head "$rollback_branch" \
  --title "Rollback deploy to $tag_name" \
  --body-file "$pr_body"
