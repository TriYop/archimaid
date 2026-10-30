# Archimaid podman deployment package: design

Date: 2026-10-05

Builds on the implemented backend and web UI. It changes no application behavior: the only code change is a container entrypoint script and a few ignore/config files.

## Purpose

Produce one archive that can be copied to a fresh machine with podman (rootless, 5.x), where a few manual commands start Archimaid (FastAPI app + PostgreSQL 16) loaded with the data that is currently in the developer's podman database (`archimaid-dev-db`, volume `archimaid-dev-data`).

## Decisions

| # | Decision |
|---|---|
| 1 | The target machine is online: it builds the app image from the packaged source and pulls `postgres:16-alpine` and the Python base image. The archive carries no image archives. |
| 2 | The deployment is a single pod described in a `podman kube play` YAML (containers: `postgres`, `app`), driven by a thin shell script that wraps each manual step. Requirements on the target: podman only (no compose provider, no systemd setup). |
| 3 | Data travels as a plain-SQL `pg_dump --no-owner --no-acl` (schema, data and `alembic_version`), not as a raw volume copy. It is loaded by Postgres' standard `/docker-entrypoint-initdb.d` hook, which runs only on an empty data directory. |
| 4 | The database is reachable only inside the pod. The app is published on host port `8000` (`ARCHIMAID_PORT`), bound to `127.0.0.1` by default (`ARCHIMAID_BIND`). The application has no authentication; exposing it with `ARCHIMAID_BIND=0.0.0.0` is the operator's explicit choice. |
| 5 | The database password is not the dev password. It comes from `ARCHIMAID_DB_PASSWORD` or is generated (32 hex characters), and is kept in a podman secret. Passwords must match `[A-Za-z0-9]+` so that they are safe inside a connection URL. |
| 6 | Re-running the deploy never touches existing data. Loading the dump again requires the explicit, confirmed `--fresh` flag. |
| 7 | The app image's entrypoint waits for the database, runs the Alembic migrations (a no-op when the schema is current), then starts uvicorn. A later release therefore upgrades the schema in place. |
| 8 | Out of scope: start at boot (Quadlet/systemd), TLS or login, offline image archives, backup scheduling, multi-host or Kubernetes deployment. |

## Files

All new; paths relative to the repo root.

| File | Role |
|---|---|
| `Containerfile` | `python:3.13-slim`; installs `uv`, then `uv sync --frozen --no-dev` from `pyproject.toml` and `uv.lock`; copies `src/`; runs as a non-root user (`archimaid`, uid 10001); `ENTRYPOINT ["/app/deploy/entrypoint.sh"]`. |
| `.containerignore` | Excludes `.git`, `.venv`, `.env`, `tests`, `docs`, `deploy/data`, caches. |
| `deploy/entrypoint.sh` | POSIX shell: builds `DATABASE_URL=postgresql+psycopg://archimaid:$POSTGRES_PASSWORD@127.0.0.1:5432/archimaid`; waits for the database (retries for up to 120 s, then exits non-zero with a clear message); runs `python -m archimaid.adapters.persistence.migrate`; `exec uvicorn archimaid.main:build_app --factory --host 0.0.0.0 --port 8000`. |
| `deploy/archimaid-pod.yaml` | The pod. A `Pod` with `postgres` (`POSTGRES_USER=archimaid`, `POSTGRES_DB=archimaid`, `POSTGRES_PASSWORD` from the secret, the named volume on `/var/lib/postgresql/data`, the dump mounted read-only at `/docker-entrypoint-initdb.d/archimaid.sql`) and `app` (the built image with `imagePullPolicy: Never`, since it is built locally; `POSTGRES_PASSWORD` from the same secret, `containerPort 8000` published on `hostPort` `@PORT@` and `hostIP` `@BIND@`). The deploy script substitutes the placeholders `@POD@`, `@SECRET@`, `@IMAGE@`, `@PORT@`, `@BIND@`, `@VOLUME@` and `@DUMP@`. Readiness is checked by `deploy.sh`, not by a probe. |
| `deploy/deploy.sh` | See "Deploy flow". |
| `deploy/export-data.sh` | See "Export flow". |
| `deploy/make-package.sh` | See "Package". |
| `deploy/README.md` | The manual steps, the options below, upgrade, reset and backup notes, and a warning that the archive contains the real data and must be handled as sensitive. |
| `.gitignore` | Adds `deploy/data/` and `dist/`. |

## Export flow (`deploy/export-data.sh`, run on this machine)

1. Inputs: `ARCHIMAID_SOURCE_CONTAINER` (default `archimaid-dev-db`), `ARCHIMAID_SOURCE_USER`/`DB` (default `archimaid`).
2. If the source container exists and is stopped, start it and remember to stop it again afterwards (an exit trap restores its previous state, also on failure). If it does not exist, fail with a clear message. The volume is never modified.
3. Wait with `pg_isready` (inside the container), then run `pg_dump --no-owner --no-acl --clean --if-exists` through `podman exec`, writing `deploy/data/archimaid.sql`. The directory `deploy/data/` is mode 700 and the dump inside it is mode 644: the unprivileged `postgres` user inside the container must be able to read the file (verified: a 600 file fails with `Permission denied`), so the private directory is what keeps other host users out. `row-counts.txt` stays 600.
4. Sanity checks on the dump: it contains `alembic_version` and the `data_flow` table, and its size is non-zero; print the row count per application table taken from the source database so the operator can compare them after deployment.

## Package (`deploy/make-package.sh`)

Builds `dist/archimaid-deploy-<YYYYMMDD>.tar.gz` containing the tracked source (`git archive HEAD`, so uncommitted changes are never shipped; the script refuses to run with a dirty tree unless `--allow-dirty` is given) plus `deploy/data/archimaid.sql`. It fails if the dump is missing. It prints the archive path, size and SHA-256.

## Deploy flow (`deploy/deploy.sh`, run on the target machine from the unpacked directory)

Options by environment: `ARCHIMAID_DB_PASSWORD`, `ARCHIMAID_PORT` (8000), `ARCHIMAID_BIND` (127.0.0.1), `ARCHIMAID_POD` (`archimaid`), `ARCHIMAID_VOLUME` (`archimaid-data`), `ARCHIMAID_IMAGE` (`localhost/archimaid:latest`). Flag: `--fresh`.

1. Check that `podman` exists and that `deploy/data/archimaid.sql` is present; validate the port and the password pattern.
2. `podman build -t "$ARCHIMAID_IMAGE" .`
3. Create the secret `<pod>-db-password` if absent (from the environment or generated); an existing secret is reused and never overwritten. It holds a Kubernetes `Secret` manifest, because podman's `secretKeyRef` rejects a bare value (verified on podman 5.4.1).
4. If the volume does not exist, create it: this is the only case where the dump will be loaded. If it exists, print that existing data is kept and the dump is ignored.
5. With `--fresh`: print what will be deleted (pod, volume), ask the operator to type `fresh`, then remove the pod and the volume and continue as for a new volume.
6. Render the YAML (substituting `@PORT@`, `@BIND@`, `@DUMP@` as an absolute path, the image and the volume name) to a temporary file and run `podman kube play --replace` on it.
7. Wait until `GET /ui/` answers (a Python `urlopen` run inside the app container, so the host needs no `curl`; up to 180 s, since the first start loads the dump); on timeout print the last lines of both container logs and exit non-zero. If the volume was new, then check the database log: a failed dump load aborts Postgres' init, podman restarts the container, and it comes up on the half-initialized volume with an empty schema that the app migrates from scratch, so "up" proves nothing. The script therefore fails (printing the init output, advising `--fresh`) when the log contains `psql: error` or lacks `init process complete`. On success print the URL and how to read the password (`podman secret inspect --showsecret archimaid-db-password`).

## Error handling

- Every script uses `set -eu`, fails with a one-line message naming the missing prerequisite or option, and never prints the password except through the explicit `secret inspect` hint.
- A failed dump load: Postgres stops initializing; the script's log excerpt shows it. The volume is then in a half-initialized state, so the README says to rerun with `--fresh`.
- An existing volume plus a different password: Postgres applies the password only when it first initializes the volume. The secret is never overwritten (step 3), so this only happens if the operator deletes the secret by hand; the app then fails its database wait with a clear message, which is the intended signal. Changing the password later needs a manual `ALTER USER` plus a new secret; the README says so.

## Testing and acceptance

Scripts are verified by running them, on this machine, in a separate namespace that cannot disturb the dev database (`ARCHIMAID_POD=archimaid-test`, `ARCHIMAID_VOLUME=archimaid-test-data`, `ARCHIMAID_PORT=18000`):

1. `export-data.sh` produces a non-empty dump and leaves `archimaid-dev-db` stopped as it found it; the dev volume is unchanged.
2. `make-package.sh` builds the archive; unpack it into a temporary directory.
3. `deploy.sh` there brings up the pod; `GET http://127.0.0.1:18000/ui/` and `/teams` succeed.
4. Row counts per table in the new database equal the source counts printed by the export, and `alembic_version` equals the latest revision.
5. A second `deploy.sh` run keeps the data (add a team through the API, rerun, the team is still there); `--fresh` with the confirmation restores the dump (the team is gone).
6. The app container runs as a non-root user and the database port is not published on the host.
7. Clean up the test pod, volume and secret afterwards.

`shellcheck` is run on the scripts when it is installed. The existing pytest suite is unchanged and must stay green.

## Open items (resolved while implementing)

- Verified on podman 5.4.1: `hostIP`, `secretKeyRef` (with a `Secret`-manifest secret), a `hostPath` file mount and a named volume all work, and volumes survive `kube play --replace` and `kube down`.
- On this development machine `kube play --replace` prints `rootless netns: kill network process: permission denied` while removing the old pod, although the pod is recreated correctly. It looks like an artifact of the restricted session this was tested in; the script does not hide or depend on it.
- Whether `python:3.13-slim` plus `uv sync --frozen` builds cleanly for `psycopg[binary]` on the target architecture (x86_64 assumed, the same as this machine).
