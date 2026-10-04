#!/bin/sh
# Deploy Archimaid in a podman pod. Usage: deploy.sh [--fresh]
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
POD=${ARCHIMAID_POD:-archimaid}
VOLUME=${ARCHIMAID_VOLUME:-archimaid-data}
IMAGE=${ARCHIMAID_IMAGE:-localhost/archimaid:latest}
PORT=${ARCHIMAID_PORT:-8000}
BIND=${ARCHIMAID_BIND:-127.0.0.1}
SECRET="${POD}-db-password"
DUMP="$HERE/data/archimaid.sql"
FRESH=0

fail() { echo "deploy: $*" >&2; exit 1; }

case "${1:-}" in
  "") ;;
  --fresh) FRESH=1 ;;
  *) fail "usage: deploy.sh [--fresh]" ;;
esac

command -v podman >/dev/null 2>&1 || fail "podman is not installed"
[ -f "$DUMP" ] || fail "missing $DUMP (run deploy/export-data.sh where the data lives, then repackage)"
case $PORT in ''|*[!0-9]*) fail "ARCHIMAID_PORT must be a number" ;; esac

echo "==> building image $IMAGE"
podman build -t "$IMAGE" "$ROOT"

if [ "$FRESH" = 1 ]; then
  printf 'This deletes pod "%s" and volume "%s" (all its data). Type "fresh" to continue: ' "$POD" "$VOLUME"
  read -r answer
  [ "$answer" = fresh ] || fail "aborted, nothing was deleted"
  podman pod rm -f "$POD" >/dev/null 2>&1 || true
  podman volume rm "$VOLUME" >/dev/null 2>&1 || true
fi

if podman secret exists "$SECRET"; then
  echo "==> secret $SECRET exists, kept"
else
  pw=${ARCHIMAID_DB_PASSWORD:-$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')}
  case $pw in ''|*[!A-Za-z0-9]*) fail "the database password must match [A-Za-z0-9]+" ;; esac
  printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: %s\ndata:\n  password: %s\n' \
    "$SECRET" "$(printf %s "$pw" | base64 | tr -d '\n')" | podman secret create "$SECRET" - >/dev/null
  echo "==> secret $SECRET created"
fi

NEW_VOLUME=0
if podman volume exists "$VOLUME"; then
  echo "==> volume $VOLUME exists: its data is kept and the dump is ignored"
else
  podman volume create "$VOLUME" >/dev/null
  NEW_VOLUME=1
  echo "==> new volume $VOLUME: the dump will be loaded on first start"
fi

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
sed -e "s|@POD@|$POD|g" -e "s|@SECRET@|$SECRET|g" -e "s|@IMAGE@|$IMAGE|g" \
    -e "s|@PORT@|$PORT|g" -e "s|@BIND@|$BIND|g" -e "s|@VOLUME@|$VOLUME|g" \
    -e "s|@DUMP@|$DUMP|g" "$HERE/archimaid-pod.yaml" > "$TMP"

echo "==> starting pod $POD"
podman kube play --replace "$TMP" >/dev/null

echo "==> waiting for the application (the first start loads the dump)"
i=0
until podman exec "${POD}-app" python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ui/', timeout=3)" \
  >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 90 ]; then
    echo "--- ${POD}-db (last lines) ---" >&2
    podman logs --tail 30 "${POD}-db" >&2 || true
    echo "--- ${POD}-app (last lines) ---" >&2
    podman logs --tail 30 "${POD}-app" >&2 || true
    fail "the application did not come up within 180 s (if the dump failed to load, rerun with --fresh)"
  fi
  sleep 2
done

if [ "$NEW_VOLUME" = 1 ]; then
  # A failed dump load aborts Postgres' init, podman restarts it, and it then starts on the
  # half-initialized volume with an empty schema: check the log instead of trusting "up".
  dblog=$(podman logs "${POD}-db" 2>&1 || true)
  if printf '%s\n' "$dblog" | grep -q 'psql: error' \
     || ! printf '%s\n' "$dblog" | grep -q 'init process complete'; then
    echo "--- ${POD}-db (init output) ---" >&2
    printf '%s\n' "$dblog" | grep -A3 -i 'archimaid.sql\|psql: error' | head -20 >&2
    fail "the data dump did not load into the new volume; fix the cause and rerun with --fresh"
  fi
fi

echo "==> Archimaid is up: http://${BIND}:${PORT}/ui/"
echo "    database password: podman secret inspect --showsecret ${SECRET}"
