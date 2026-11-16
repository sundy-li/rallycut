#!/usr/bin/env bash
# Print Go -ldflags that stamp version / commit / build time into the binary
# (see backend/buildinfo). Usage: scripts/build-ldflags.sh [version]
set -euo pipefail
cd "$(dirname "$0")/.."

version="${1:-${VERSION:-}}"
if [[ -z "$version" ]]; then
  # Only app release tags count; model-* mirror tags may share the commit.
  version="$(git describe --tags --match 'v[0-9]*' --abbrev=0 2>/dev/null || echo 0.1.0)"
fi
version="${version#v}"
commit="$(git rev-parse --short=12 HEAD 2>/dev/null || true)"
dirty=false
if [[ -n "$commit" && -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ]]; then
  dirty=true
fi
built="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
pkg=rallycut/backend/buildinfo
printf '%s' "-X $pkg.Version=$version -X $pkg.Commit=$commit -X $pkg.Dirty=$dirty -X $pkg.BuildTime=$built"
