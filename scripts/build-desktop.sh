#!/usr/bin/env bash
# Wails dev and build share build/bin. Publish an independent production copy.
set -euo pipefail
cd "$(dirname "$0")/.."
wails build -clean

if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Production binary built in build/bin.'
  exit 0
fi

source_app="$PWD/build/bin/RallyCut.app"
verify_production() {
  local tags
  tags="$(go version -m "$1/Contents/MacOS/RallyCut" | awk '$1 == "build" && $2 ~ /^-tags=/ {print $2}')"
  if [[ ! "$tags" =~ (^|[=,])production([,[:space:]]|$) ]] || [[ "$tags" =~ (^|[=,])dev([,[:space:]]|$) ]]; then
    echo 'Refusing to publish a non-production binary. Stop concurrent wails dev and rebuild.' >&2
    return 1
  fi
}
verify_production "$source_app"

mkdir -p build/release
stage="$(mktemp -d "$PWD/build/release/.rallycut-XXXXXX")"
trap 'rm -rf "$stage"' EXIT
ditto "$source_app" "$stage/RallyCut.app"
verify_production "$stage/RallyCut.app"
codesign --verify --deep --strict "$stage/RallyCut.app"
rm -rf "$PWD/build/release/RallyCut.app"
mv "$stage/RallyCut.app" "$PWD/build/release/RallyCut.app"
echo "Standalone app: $PWD/build/release/RallyCut.app"
echo 'Run: just run (this copy is not overwritten by wails dev)'
