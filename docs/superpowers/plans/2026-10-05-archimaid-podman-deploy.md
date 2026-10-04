# Podman deployment package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One archive that deploys Archimaid (app + PostgreSQL 16) on a fresh rootless podman machine with a few manual commands, loaded with the data currently in the dev podman database.

**Architecture:** An app image (`Containerfile` + a waiting/migrating entrypoint), a `podman kube play` pod YAML (Postgres + app, named volume, dump loaded through Postgres' `docker-entrypoint-initdb.d`), and thin POSIX shell scripts: `export-data.sh` (pg_dump from the current dev container), `deploy.sh` (build, secret, volume, kube play, wait), `make-package.sh` (tarball from `git archive` plus the dump).

**Tech Stack:** podman 5.x (rootless), POSIX `sh`, `python:3.13-slim`, `uv`, `postgres:16-alpine`, Alembic.

**Spec:** `docs/superpowers/specs/2026-10-05-archimaid-podman-deploy-design.md` (it wins over this plan where they differ; Task 3 amends it with three facts learned while planning).

## Global Constraints

- Target: rootless podman 5.x, online (pulls images, installs Python deps); no compose provider, no systemd setup, no Node.
- The app image runs as a non-root user (uid 10001); the database port is never published on the host.
- The app has no authentication: default bind is `127.0.0.1` (`ARCHIMAID_BIND`), default port `8000` (`ARCHIMAID_PORT`).
- Database password: from `ARCHIMAID_DB_PASSWORD` or generated (24 random bytes as hex); must match `[A-Za-z0-9]+`; never printed by the scripts.
- Re-running `deploy.sh` never touches existing data; the dump loads only into a new empty volume; `--fresh` requires typing `fresh`.
- Scripts are POSIX `sh` with `set -eu`, fail with a one-line `<script>: <message>` on stderr, and are executable (mode 755 committed).
- The dump (`deploy/data/`) and `dist/` are git-ignored; the dump file has mode 600.
- All verification runs in a test namespace that cannot disturb the dev database: `ARCHIMAID_POD=archimaid-test`, `ARCHIMAID_VOLUME=archimaid-test-data`, `ARCHIMAID_PORT=18000`, image `localhost/archimaid-test:latest`. The dev container `archimaid-dev-db` and volume `archimaid-dev-data` are only ever read (the container is started for the dump and stopped again).
- The existing pytest suite stays green and is unchanged; run `uv run pytest -q`, `uv run ruff check src tests`, `uv run mypy src` at the end.
- Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Re-running `deploy.sh` (and re-running with a different `ARCHIMAID_DB_PASSWORD`) must keep data and never reload the dump (Task 3 acceptance).
2. `export-data.sh` must leave `archimaid-dev-db` stopped if it found it stopped, even when the dump fails, and must never modify the volume (Task 2).
3. The password must not appear in script output, in the rendered YAML, or in the image build context/args (Task 3).
4. A failed dump load or a dead database must produce a visible error with log excerpts, not a hang or an empty working app (Tasks 1 and 3).
5. The container must run non-root, and only the app port may be published (Tasks 1 and 4).
6. `make-package.sh` must refuse a dirty tree and a missing dump, and the archive must contain the deploy files with exec bits (Task 4).

## File Structure

| File | Responsibility |
|---|---|
| `Containerfile`, `.containerignore` | the app image |
| `deploy/entrypoint.sh` | wait for DB, migrate, start uvicorn |
| `deploy/row-counts.sql` | one query printing `table count` per table; used on both sides to compare data |
| `deploy/export-data.sh` | dump the dev database into `deploy/data/` |
| `deploy/archimaid-pod.yaml` | the pod template with `@...@` placeholders |
| `deploy/deploy.sh` | manual deployment steps |
| `deploy/make-package.sh` | build `dist/archimaid-deploy-<date>.tar.gz` |
| `deploy/README.md` | operator documentation |
| `.gitignore`, `CLAUDE.md` | ignore rules, a short Deployment section |

---

### Task 1: App image and entrypoint

**Files:**
- Create: `Containerfile`, `.containerignore`, `deploy/entrypoint.sh`
- Modify: `.gitignore`

**Interfaces:**
- Produces: an image whose entrypoint reads `POSTGRES_PASSWORD` (required), `ARCHIMAID_DB_HOST` (default `127.0.0.1`), `ARCHIMAID_DB_WAIT` (seconds, default `120`); it connects as user/db `archimaid` on port 5432, runs migrations, then serves on port 8000.

- [ ] **Step 1: Write the failing checks (the image does not exist yet)**

Run:
```bash
podman build -t localhost/archimaid-test:latest . 2>&1 | tail -3
```
Expected: FAIL (`no Containerfile`/`no such file`).

- [ ] **Step 2: Create the files**

`.containerignore`:
```
.git
.venv
.env
.claude
.superpowers
tests
docs
dist
deploy/data
__pycache__
*.pyc
.pytest_cache
.ruff_cache
.mypy_cache
*.egg-info
```

`Containerfile`:
```dockerfile
FROM docker.io/library/python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

COPY deploy/entrypoint.sh /app/deploy/entrypoint.sh
RUN chmod 755 /app/deploy/entrypoint.sh \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin archimaid

USER 10001
EXPOSE 8000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
```

`deploy/entrypoint.sh` (then `chmod 755 deploy/entrypoint.sh`):
```sh
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
```

Append to `.gitignore`:
```
deploy/data/
dist/
```

- [ ] **Step 3: Build and check**

Run:
```bash
chmod 755 deploy/entrypoint.sh
podman build -t localhost/archimaid-test:latest . 2>&1 | tail -3
podman run --rm --entrypoint id localhost/archimaid-test:latest -u
podman run --rm localhost/archimaid-test:latest; echo "exit=$?"
podman run --rm -e POSTGRES_PASSWORD=x -e ARCHIMAID_DB_WAIT=3 localhost/archimaid-test:latest; echo "exit=$?"
podman run --rm --entrypoint python localhost/archimaid-test:latest -c "import archimaid, psycopg; print('import ok')"
```
Expected: the build succeeds; `id -u` prints `10001`; the third command prints `entrypoint: POSTGRES_PASSWORD is not set` and `exit=1`; the fourth prints `entrypoint: database not reachable at 127.0.0.1:5432 after 3s: ...` and `exit=1` (no traceback, no password in the message); the last prints `import ok`. If the `uv sync` step fails on `psycopg[binary]`, report the error (spec open item) and rule on the smallest fix (for example installing `libpq5`).

- [ ] **Step 4: Commit**

```bash
git add Containerfile .containerignore deploy/entrypoint.sh .gitignore
git commit -m "feat(deploy): app container image with a wait-and-migrate entrypoint

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Export the current data

**Files:**
- Create: `deploy/row-counts.sql`, `deploy/export-data.sh`
- Test: manual run against `archimaid-dev-db` (read-only)

**Interfaces:**
- Produces: `deploy/data/archimaid.sql` (plain-SQL dump, mode 600) and `deploy/data/row-counts.txt` (lines `<table> <count>`, sorted by table). `deploy/row-counts.sql` prints exactly that format and is reused on the target side.

- [ ] **Step 1: Write the failing check**

Run: `sh deploy/export-data.sh`
Expected: FAIL (`No such file`).

- [ ] **Step 2: Create the files**

`deploy/row-counts.sql`:
```sql
SELECT table_name || ' ' ||
       (xpath('/row/c/text()',
              query_to_xml(format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name),
                           false, true, '')))[1]::text
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name;
```

`deploy/export-data.sh` (then `chmod 755`):
```sh
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
```

- [ ] **Step 3: Run it and verify**

Run:
```bash
chmod 755 deploy/export-data.sh
podman ps -a --filter name=archimaid-dev-db --format '{{.Status}}'
sh deploy/export-data.sh
podman ps -a --filter name=archimaid-dev-db --format '{{.Status}}'
ls -l deploy/data
sh deploy/export-data.sh   # second run, same result
ARCHIMAID_SOURCE_CONTAINER=nope sh deploy/export-data.sh; echo "exit=$?"
```
Expected: the container shows `Exited ...` before and after the first run (the script started and stopped it); the output lists one `<table> <count>` line per table (team, team_member, application, function, data_type, data_flow, technology, persona, plus catalog tables and `alembic_version 1`), and `ls -l` shows `-rw-------` for `archimaid.sql`; the last command prints `export-data: container nope not found ...` and `exit=1`. Check `grep -c . deploy/data/row-counts.txt` is above 8 and `grep alembic_version deploy/data/row-counts.txt` shows `alembic_version 1`. The migration head is `0003`, so confirm the source database is at the latest revision: `grep -A2 'COPY public.alembic_version' deploy/data/archimaid.sql` must show `0003`. If it shows an older revision, that is fine (the entrypoint migrates at startup); note it in the ledger.

- [ ] **Step 4: Commit**

```bash
git add deploy/row-counts.sql deploy/export-data.sh
git commit -m "feat(deploy): export the current dev database as a plain-SQL dump

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

(`deploy/data/` is git-ignored, so the dump is not committed.)

---

### Task 3: The pod and the deploy script

**Files:**
- Create: `deploy/archimaid-pod.yaml`, `deploy/deploy.sh`
- Modify: `docs/superpowers/specs/2026-10-05-archimaid-podman-deploy-design.md` (three amendments)

**Interfaces:**
- Consumes: the image from Task 1 (entrypoint env contract), `deploy/data/archimaid.sql` from Task 2.
- Produces: `deploy/deploy.sh [--fresh]` with environment options `ARCHIMAID_DB_PASSWORD`, `ARCHIMAID_PORT` (8000), `ARCHIMAID_BIND` (127.0.0.1), `ARCHIMAID_POD` (`archimaid`), `ARCHIMAID_VOLUME` (`archimaid-data`), `ARCHIMAID_IMAGE` (`localhost/archimaid:latest`). Containers are named `<pod>-db` and `<pod>-app`; the secret is named `<pod>-db-password` and holds a Kubernetes `Secret` manifest (podman's `secretKeyRef` requires that form, verified on podman 5.4.1).

- [ ] **Step 1: Write the failing check**

Run: `sh deploy/deploy.sh`
Expected: FAIL (`No such file`).

- [ ] **Step 2: Create the pod template**

`deploy/archimaid-pod.yaml`:
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: "@POD@"
spec:
  containers:
    - name: db
      image: docker.io/library/postgres:16-alpine
      env:
        - name: POSTGRES_USER
          value: archimaid
        - name: POSTGRES_DB
          value: archimaid
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: "@SECRET@"
              key: password
      volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
        - name: dump
          mountPath: /docker-entrypoint-initdb.d/archimaid.sql
          readOnly: true
    - name: app
      image: "@IMAGE@"
      imagePullPolicy: Never
      env:
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: "@SECRET@"
              key: password
      ports:
        - containerPort: 8000
          hostPort: @PORT@
          hostIP: "@BIND@"
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: "@VOLUME@"
    - name: dump
      hostPath:
        path: "@DUMP@"
        type: File
```

- [ ] **Step 3: Create the deploy script**

`deploy/deploy.sh` (then `chmod 755`):
```sh
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

if podman volume exists "$VOLUME"; then
  echo "==> volume $VOLUME exists: its data is kept and the dump is ignored"
else
  podman volume create "$VOLUME" >/dev/null
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

echo "==> Archimaid is up: http://${BIND}:${PORT}/ui/"
echo "    database password: podman secret inspect --showsecret ${SECRET}"
```

- [ ] **Step 4: Amend the spec**

In `docs/superpowers/specs/2026-10-05-archimaid-podman-deploy-design.md`:
1. In the `deploy/archimaid-pod.yaml` row, add that the app container has `imagePullPolicy: Never` (the image is built locally) and that the placeholders are `@POD@`, `@SECRET@`, `@IMAGE@`, `@PORT@`, `@BIND@`, `@VOLUME@`, `@DUMP@`; remove the `pg_isready` readiness-probe mention (readiness is checked by `deploy.sh`).
2. In "Deploy flow" step 3, replace the sentence about the secret with: the secret is named `<pod>-db-password` and holds a Kubernetes `Secret` manifest (verified: podman 5.4.1 `secretKeyRef` rejects a bare value); step 7 waits by running a Python `urlopen` of `/ui/` inside the app container (no `curl` needed on the host).
3. In "Open items", replace the `hostIP`/`secretKeyRef` bullet with: "Verified on podman 5.4.1: `hostIP`, `secretKeyRef` (with a `Secret`-manifest secret), a `hostPath` file mount and a named volume all work, and volumes survive `kube play --replace` and `kube down`."

- [ ] **Step 5: Acceptance in the test namespace**

Set the environment once for these commands:
```bash
export ARCHIMAID_POD=archimaid-test ARCHIMAID_VOLUME=archimaid-test-data ARCHIMAID_PORT=18000 ARCHIMAID_IMAGE=localhost/archimaid-test:latest
chmod 755 deploy/deploy.sh
sh deploy/deploy.sh 2>&1 | tail -12
```
Expected: ends with `==> Archimaid is up: http://127.0.0.1:18000/ui/`. If `kube play` rejects a field, report the error and rule on the smallest supported alternative, amending the spec's open items.

Then verify:
```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18000/teams          # 200
podman exec -i archimaid-test-db psql -U archimaid -d archimaid -At < deploy/row-counts.sql | diff - deploy/data/row-counts.txt && echo COUNTS-EQUAL
podman port archimaid-test-app                                                   # only 8000/tcp -> 127.0.0.1:18000
podman exec archimaid-test-app id -u                                             # 10001
podman inspect archimaid-test-db --format '{{json .HostConfig.PortBindings}}'    # {} (not published)
sh deploy/deploy.sh 2>&1 | grep -E 'kept|ignored'                                # secret kept, volume kept, dump ignored
```
Then check data survives a re-run and a changed password does not matter:
```bash
curl -s -X POST http://127.0.0.1:18000/teams -H 'content-type: application/json' -d '{"name":"plan-marker"}' | head -c 80
ARCHIMAID_DB_PASSWORD=Different123 sh deploy/deploy.sh >/dev/null 2>&1
curl -s http://127.0.0.1:18000/teams | grep -c plan-marker                      # 1: data kept
printf 'no\n' | sh deploy/deploy.sh --fresh; echo "exit=$?"                       # aborted, exit 1, marker still there
curl -s http://127.0.0.1:18000/teams | grep -c plan-marker                      # 1
printf 'fresh\n' | sh deploy/deploy.sh --fresh 2>&1 | tail -3
curl -s http://127.0.0.1:18000/teams | grep -c plan-marker                      # 0: dump reloaded
podman exec -i archimaid-test-db psql -U archimaid -d archimaid -At < deploy/row-counts.sql | diff - deploy/data/row-counts.txt && echo COUNTS-EQUAL
```
Also check that the password is not in the rendered file or the output: `sh deploy/deploy.sh 2>&1 | grep -c "$(podman secret inspect --showsecret archimaid-test-db-password | grep -o 'password: .*' | cut -d' ' -f2 | base64 -d)"` must print `0`.
Expected as annotated in the comments. Then clean up the test namespace:
```bash
podman pod rm -f archimaid-test >/dev/null; podman volume rm archimaid-test-data >/dev/null; podman secret rm archimaid-test-db-password >/dev/null; podman rmi localhost/archimaid-test:latest >/dev/null
unset ARCHIMAID_POD ARCHIMAID_VOLUME ARCHIMAID_PORT ARCHIMAID_IMAGE
```
Confirm the dev objects are untouched: `podman ps -a --filter name=archimaid-dev-db --format '{{.Status}}'` still `Exited`, and `podman volume ls | grep archimaid-dev-data` still lists the volume.

- [ ] **Step 6: Commit**

```bash
git add deploy/archimaid-pod.yaml deploy/deploy.sh docs/superpowers/specs/2026-10-05-archimaid-podman-deploy-design.md
git commit -m "feat(deploy): pod YAML and deploy script; spec amendments from verification

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Package, README, final acceptance

**Files:**
- Create: `deploy/make-package.sh`, `deploy/README.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: `deploy/data/archimaid.sql` and `deploy/data/row-counts.txt` (Task 2), `deploy/deploy.sh` (Task 3).
- Produces: `dist/archimaid-deploy-<YYYYMMDD>.tar.gz` containing the tracked source at `HEAD` plus `deploy/data/`.

- [ ] **Step 1: Write the failing check**

Run: `sh deploy/make-package.sh`
Expected: FAIL (`No such file`).

- [ ] **Step 2: Create the package script**

`deploy/make-package.sh` (then `chmod 755`):
```sh
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
mkdir -p "$STAGE/$NAME/deploy/data"
cp "$DATA"/* "$STAGE/$NAME/deploy/data/"
chmod 600 "$STAGE/$NAME/deploy/data/archimaid.sql"
tar -C "$STAGE" -czf "dist/$NAME.tar.gz" "$NAME"

echo "==> dist/$NAME.tar.gz ($(wc -c < "dist/$NAME.tar.gz") bytes)"
sha256sum "dist/$NAME.tar.gz"
echo "==> the archive contains the real data: handle it as sensitive"
```

- [ ] **Step 3: Create the README**

`deploy/README.md`:
````markdown
# Deploying Archimaid with podman

Needs podman (rootless is fine) and internet access on the target machine. The package contains the source and a copy of the data; **it holds real data, so keep and transfer it as sensitive material.**

## On the machine that has the data

```sh
sh deploy/export-data.sh      # dumps archimaid-dev-db into deploy/data/ (the container is stopped again afterwards)
sh deploy/make-package.sh     # writes dist/archimaid-deploy-<date>.tar.gz
```

Copy the archive to the new machine (for example with `scp`).

## On the new machine

```sh
tar xzf archimaid-deploy-<date>.tar.gz
cd archimaid-deploy-<date>
sh deploy/deploy.sh
```

It builds the image, creates a volume and a database password secret, starts the pod (PostgreSQL 16 + the app), loads the data on the first start and prints the URL (default `http://127.0.0.1:8000/ui/`).

Options (environment variables): `ARCHIMAID_PORT` (8000), `ARCHIMAID_BIND` (127.0.0.1), `ARCHIMAID_DB_PASSWORD` (generated if unset, letters and digits only), `ARCHIMAID_POD` (`archimaid`), `ARCHIMAID_VOLUME` (`archimaid-data`), `ARCHIMAID_IMAGE` (`localhost/archimaid:latest`).

**The application has no login.** It listens on `127.0.0.1` only. Use `ARCHIMAID_BIND=0.0.0.0` only on a network you trust, or put a reverse proxy with authentication in front.

## Verify the data

```sh
podman exec -i archimaid-db psql -U archimaid -d archimaid -At < deploy/row-counts.sql | diff - deploy/data/row-counts.txt && echo "same rows as the source"
```

## Operations

- **Show the database password:** `podman secret inspect --showsecret archimaid-db-password`
- **Logs:** `podman logs archimaid-app`, `podman logs archimaid-db`
- **Stop / start:** `podman pod stop archimaid` / `podman pod start archimaid`
- **Upgrade to a new release:** unpack the new archive and run `sh deploy/deploy.sh` again. The image is rebuilt, the pod recreated, the data kept (the dump is ignored because the volume exists) and the database schema is migrated on startup.
- **Start again from the packaged data:** `sh deploy/deploy.sh --fresh` deletes the pod and the volume (it asks you to type `fresh`) and reloads the dump.
- **If the first start failed** while loading the dump, the volume is half-initialized: run `sh deploy/deploy.sh --fresh`.
- **Changing the database password later** needs `ALTER USER archimaid PASSWORD '...'` in the database, then deleting and recreating the podman secret (`podman secret rm archimaid-db-password`, then `ARCHIMAID_DB_PASSWORD=... sh deploy/deploy.sh`).
- **Backup:** `podman exec archimaid-db pg_dump -U archimaid -d archimaid --no-owner --no-acl > backup.sql`
- **Remove everything:** `podman pod rm -f archimaid; podman volume rm archimaid-data; podman secret rm archimaid-db-password`
````

- [ ] **Step 4: Add a Deployment section to `CLAUDE.md`**

After the "Test configuration" section add:

```markdown
## Deployment

`deploy/` packages the app for a fresh podman machine (`deploy/README.md`): `Containerfile` (image; `deploy/entrypoint.sh` waits for the DB, migrates, serves), `deploy/archimaid-pod.yaml` (`podman kube play` pod: Postgres + app), `deploy/deploy.sh` (manual steps), `deploy/export-data.sh` (dump of the dev database into git-ignored `deploy/data/`), `deploy/make-package.sh` (tarball in `dist/`). Spec: `docs/superpowers/specs/2026-10-05-archimaid-podman-deploy-design.md`. The podman secret holds a Kubernetes `Secret` manifest because `secretKeyRef` requires it.
```

- [ ] **Step 5: Run the final acceptance**

```bash
chmod 755 deploy/make-package.sh
git add deploy CLAUDE.md && git commit -m "feat(deploy): package script, README and CLAUDE.md section

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
sh deploy/make-package.sh 2>&1 | tail -4
```
Expected: the archive path, size and SHA-256 are printed (the unrelated untracked `.claude/` folder does not matter: only tracked changes and untracked deployment files are checked). Then prove the dirty-tree refusal: `echo x >> README.md; sh deploy/make-package.sh; echo "exit=$?"; git checkout README.md` prints `make-package: uncommitted changes are not packaged ...` and `exit=1`.

Prove the refusals and the archive:
```bash
mv deploy/data/archimaid.sql /tmp/archimaid.sql.bak; sh deploy/make-package.sh; echo "exit=$?"; mv /tmp/archimaid.sql.bak deploy/data/archimaid.sql
sh deploy/make-package.sh | tail -3
tar tzf dist/archimaid-deploy-*.tar.gz | grep -E 'deploy/(deploy.sh|data/archimaid.sql|data/row-counts.txt|entrypoint.sh)|Containerfile$'
tar tvzf dist/archimaid-deploy-*.tar.gz | grep -E 'deploy/(deploy|export-data|make-package|entrypoint).sh' | cut -c1-10
tar tvzf dist/archimaid-deploy-*.tar.gz | grep 'data/archimaid.sql' | cut -c1-10
```
Expected: the missing-dump run prints `make-package: missing or empty ...` and `exit=1`; the archive lists the files above; the scripts show `-rwxr-xr-x`; the dump shows `-rw-------`.

Then the full fresh-machine rehearsal from the archive (test namespace, a new empty directory standing in for the new machine):
```bash
rm -rf /tmp/rehearsal && mkdir /tmp/rehearsal && tar xzf dist/archimaid-deploy-*.tar.gz -C /tmp/rehearsal && cd /tmp/rehearsal/archimaid-deploy-*
ARCHIMAID_POD=archimaid-test ARCHIMAID_VOLUME=archimaid-test-data ARCHIMAID_PORT=18000 ARCHIMAID_IMAGE=localhost/archimaid-test:latest sh deploy/deploy.sh 2>&1 | tail -4
podman exec -i archimaid-test-db psql -U archimaid -d archimaid -At < deploy/row-counts.sql | diff - deploy/data/row-counts.txt && echo COUNTS-EQUAL
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18000/ui/teams
```
Expected: `Archimaid is up`, `COUNTS-EQUAL`, `200`. Then clean up exactly as at the end of Task 3 Step 5, `rm -rf /tmp/rehearsal`, and return to the repo root.

Finally the repository checks: `uv run pytest -q && uv run ruff check src tests && uv run mypy src` (all green, unchanged), and `git status --short` shows only the unrelated untracked `.claude/`.

- [ ] **Step 6: Commit any fixes**

If the rehearsal required fixes, commit them (`fix(deploy): ...` with the Co-Authored-By line); otherwise there is nothing more to commit.
