#!/bin/sh
# Build dist/archimaid-deploy-<date>.tar.gz: tracked source at HEAD plus the data dump.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
DATA="$HERE/data"
ALLOW_DIRTY=0

fail() { echo "make-package: $*" >&2; exit 1; }

case "${1:-}" in
  "") ;;
  --allow-dirty) ALLOW_DIRTY=1 ;;
  *) fail "usage: make-package.sh [--allow-dirty]" ;;
esac

[ -s "$DATA/archimaid.sql" ] || fail "missing or empty $DATA/archimaid.sql (run deploy/export-data.sh first)"
cd "$ROOT"
untracked=$(git status --porcelain -- Containerfile .containerignore deploy | grep '^??' || true)
[ -z "$untracked" ] || fail "untracked deployment files would be left out: $untracked"
if [ "$ALLOW_DIRTY" = 0 ] && [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  fail "uncommitted changes are not packaged; commit them or pass --allow-dirty to package HEAD anyway"
fi

NAME="archimaid-deploy-$(date +%Y%m%d)"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p dist
git archive --format=tar --prefix="$NAME/" HEAD | tar -x -C "$STAGE"
mkdir -m 700 "$STAGE/$NAME/deploy/data"
cp "$DATA"/* "$STAGE/$NAME/deploy/data/"
chmod 644 "$STAGE/$NAME/deploy/data/archimaid.sql"
tar -C "$STAGE" -czf "dist/$NAME.tar.gz" "$NAME"

echo "==> dist/$NAME.tar.gz ($(wc -c < "dist/$NAME.tar.gz") bytes)"
sha256sum "dist/$NAME.tar.gz"
echo "==> the archive contains the real data: handle it as sensitive"
