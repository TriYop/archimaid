#!/bin/sh
# Container entrypoint: wait for the database, migrate, serve.
set -eu

fail() { echo "entrypoint: $*" >&2; exit 1; }

[ -n "${POSTGRES_PASSWORD:-}" ] || fail "POSTGRES_PASSWORD is not set"
DB_HOST=${ARCHIMAID_DB_HOST:-127.0.0.1}
export DATABASE_URL="postgresql+psycopg://archimaid:${POSTGRES_PASSWORD}@${DB_HOST}:5432/archimaid"
export ARCHIMAID_DB_HOST="$DB_HOST"

python - <<'PY'
import os
import sys
import time

import psycopg

host = os.environ["ARCHIMAID_DB_HOST"]
wait = int(os.environ.get("ARCHIMAID_DB_WAIT", "120"))
dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
deadline = time.monotonic() + wait
while True:
    try:
        psycopg.connect(dsn, connect_timeout=3).close()
        break
    except psycopg.OperationalError as exc:
        if time.monotonic() >= deadline:
            sys.exit(f"entrypoint: database not reachable at {host}:5432 after {wait}s: {exc}")
        time.sleep(2)
PY

python -m archimaid.adapters.persistence.migrate
exec uvicorn archimaid.main:build_app --factory --host 0.0.0.0 --port 8000
