#!/bin/sh
# Build dist/archimaid-deploy-<date>.tar.gz: tracked source at HEAD plus the data dump.
# With --no-data: dist/archimaid-deploy-empty-<date>.tar.gz, source only (deploys an empty instance).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
DATA="$HERE/data"
ALLOW_DIRTY=0
NO_DATA=0

fail() { echo "make-package: $*" >&2; exit 1; }

for arg in "$@"; do
  case $arg in
    --allow-dirty) ALLOW_DIRTY=1 ;;
    --no-data) NO_DATA=1 ;;
    *) fail "usage: make-package.sh [--allow-dirty] [--no-data]" ;;
  esac
done

[ "$NO_DATA" = 1 ] || [ -s "$DATA/archimaid.sql" ] || fail "missing or empty $DATA/archimaid.sql (run deploy/export-data.sh first)"
cd "$ROOT"
untracked=$(git status --porcelain -- Containerfile .containerignore deploy | grep '^??' || true)
[ -z "$untracked" ] || fail "untracked deployment files would be left out: $untracked"
if [ "$ALLOW_DIRTY" = 0 ] && [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  fail "uncommitted changes are not packaged; commit them or pass --allow-dirty to package HEAD anyway"
fi

NAME="archimaid-deploy-$([ "$NO_DATA" = 1 ] && echo empty-)$(date +%Y%m%d)"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p dist
git archive --format=tar --prefix="$NAME/" HEAD | tar -x -C "$STAGE"
if [ "$NO_DATA" = 0 ]; then
  mkdir -m 700 "$STAGE/$NAME/deploy/data"
  cp "$DATA"/* "$STAGE/$NAME/deploy/data/"
  chmod 644 "$STAGE/$NAME/deploy/data/archimaid.sql"
fi
tar -C "$STAGE" -czf "dist/$NAME.tar.gz" "$NAME"

echo "==> dist/$NAME.tar.gz ($(wc -c < "dist/$NAME.tar.gz") bytes)"
sha256sum "dist/$NAME.tar.gz"
[ "$NO_DATA" = 1 ] || echo "==> the archive contains the real data: handle it as sensitive"
