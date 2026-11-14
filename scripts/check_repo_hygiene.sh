#!/usr/bin/env bash
# Fails if tracked files look like sponsor data, secrets or large binaries.
# This repo goes public at submission and the sponsor terms forbid exposing their data,
# so this runs in `make check` and in CI.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
fail=0

report() {
  echo "hygiene: $1" >&2
  fail=1
}

files="$(git ls-files)"

# 1. Paths and file types that hold sponsor data, caches or indexes.
forbidden='(^|/)(data|mp_out)/|(^|/)models_index\.csv$|(^|/)residential-listings\.csv$|\.(faiss|index|npy|npz|pt|pth|ply|xyz|obj|dxf|zip)$'
while IFS= read -r path; do
  [ -n "$path" ] && report "sponsor data or cache file is tracked: $path"
done < <(printf '%s\n' "$files" | grep -E "$forbidden" || true)

# 2. Env files other than the example.
while IFS= read -r path; do
  [ -n "$path" ] && report "env file is tracked: $path"
done < <(printf '%s\n' "$files" | grep -E '(^|/)\.env($|\.)' | grep -v -E '(^|/)\.env\.example$' || true)

# 3. Filled-in credentials anywhere in tracked text.
secret_names='MATTERPORT_API_KEY|MATTERPORT_API_TOKEN|MATTERPORT_SDK_KEY|VEXCEL_API_KEY|COSTAR_ZIP_PASSWORD|ANTHROPIC_API_KEY'
while IFS= read -r hit; do
  [ -n "$hit" ] && report "credential value is tracked: ${hit%%=*}=<redacted>"
done < <(git grep -n -I -E "^[[:space:]]*(export[[:space:]]+)?(${secret_names})=[^[:space:]]+" -- . || true)

# 4. Anything over 1 MB (a panorama, a point cloud, a model checkpoint).
while IFS= read -r path; do
  [ -f "$path" ] || continue
  size=$(wc -c <"$path" | tr -d ' ')
  if [ "$size" -gt 1048576 ]; then
    report "file over 1 MB is tracked ($size bytes): $path"
  fi
done < <(printf '%s\n' "$files")

# 5. No AI co-author or attribution lines in any commit message (team rule, no exceptions).
attr='co-authored-by|generated with \[?claude|noreply@anthropic\.com|🤖'
while IFS= read -r sha; do
  [ -n "$sha" ] && report "commit $sha has an AI co-author or attribution line; reword it (git rebase -i, then push)"
done < <(git log --format='%h %B%x00' 2>/dev/null | tr '\n' ' ' | tr '\0' '\n' | grep -iE "$attr" | cut -d' ' -f1 || true)

if [ "$fail" -ne 0 ]; then
  echo "hygiene: FAILED. Remove the files above from git (and from history if already pushed)." >&2
  exit 1
fi
echo "hygiene: ok"
