#!/bin/sh
# Dump the current dev database (plain SQL) into deploy/data/. Read-only for the source.
set -eu

CONTAINER=${ARCHIMAID_SOURCE_CONTAINER:-archimaid-dev-db}
DB_USER=${ARCHIMAID_SOURCE_USER:-archimaid}
DB_NAME=${ARCHIMAID_SOURCE_DB:-archimaid}
HERE=$(cd "$(dirname "$0")" && pwd)
OUT="$HERE/data/archimaid.sql"
COUNTS="$HERE/data/row-counts.txt"

fail() { echo "export-data: $*" >&2; exit 1; }

command -v podman >/dev/null 2>&1 || fail "podman is not installed"
state=$(podman container inspect --format '{{.State.Status}}' "$CONTAINER" 2>/dev/null) \
  || fail "container $CONTAINER not found (set ARCHIMAID_SOURCE_CONTAINER)"

if [ "$state" != running ]; then
  echo "==> starting $CONTAINER (it will be stopped again afterwards)"
  podman start "$CONTAINER" >/dev/null
  trap 'podman stop "$CONTAINER" >/dev/null' EXIT
fi

i=0
until podman exec "$CONTAINER" pg_isready -q -U "$DB_USER" -d "$DB_NAME"; do
  i=$((i + 1))
  [ "$i" -le 30 ] || fail "database in $CONTAINER did not become ready"
  sleep 1
done

mkdir -p "$HERE/data"
umask 077
echo "==> dumping $DB_NAME from $CONTAINER"
podman exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" \
  --no-owner --no-acl --clean --if-exists > "$OUT.tmp" || { rm -f "$OUT.tmp"; fail "pg_dump failed"; }

[ -s "$OUT.tmp" ] || { rm -f "$OUT.tmp"; fail "the dump is empty"; }
grep -q 'alembic_version' "$OUT.tmp" || { rm -f "$OUT.tmp"; fail "the dump has no alembic_version"; }
grep -q 'data_flow' "$OUT.tmp" || { rm -f "$OUT.tmp"; fail "the dump has no data_flow table"; }
mv "$OUT.tmp" "$OUT"

podman exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -At < "$HERE/row-counts.sql" > "$COUNTS" \
  || fail "could not count rows"

echo "==> wrote $OUT ($(wc -c < "$OUT") bytes)"
echo "==> row counts at the source (also in $COUNTS):"
cat "$COUNTS"
