# Deploying Archimaid with podman

Needs podman (rootless is fine) and internet access on the target machine. The package contains the source and a copy of the data; **it holds real data, so keep and transfer it as sensitive material.**

## On the machine that has the data

```sh
sh deploy/export-data.sh      # dumps archimaid-dev-db into deploy/data/ (the container is stopped again afterwards)
sh deploy/make-package.sh     # writes dist/archimaid-deploy-<date>.tar.gz (commit your changes first)
```

Copy the archive to the new machine (for example with `scp`).

## On the new machine

```sh
tar xzf archimaid-deploy-<date>.tar.gz
cd archimaid-deploy-<date>
sh deploy/deploy.sh
```

It builds the image, creates a volume and a database password secret, starts the pod (PostgreSQL 16 + the app), loads the data on the first start and prints the URL (default `http://127.0.0.1:8000/ui/`). On a first start it also checks that the data really loaded and fails with the database log if not.

Options (environment variables): `ARCHIMAID_PORT` (8000), `ARCHIMAID_BIND` (127.0.0.1), `ARCHIMAID_DB_PASSWORD` (generated if unset, letters and digits only), `ARCHIMAID_POD` (`archimaid`), `ARCHIMAID_VOLUME` (`archimaid-data`), `ARCHIMAID_IMAGE` (`localhost/archimaid:latest`).

**The application has no login.** It listens on `127.0.0.1` only. Use `ARCHIMAID_BIND=0.0.0.0` only on a network you trust, or put a reverse proxy with authentication in front.

`deploy/data/` is a private directory (mode 700): the dump inside it is world-readable so that the database inside the container can read it, and the directory is what keeps other users of the machine out. Delete the unpacked `deploy/data/` once the data is loaded if you do not need it again.

## Empty instance (no data)

If `deploy/data/archimaid.sql` is absent, `deploy.sh` deploys an empty instance: the application creates the schema on first start and the migrations seed the reference data (confidentiality, integrity, availability and traceability levels, function categories, usage modes, technology types, tech standard statuses), with no teams, applications or other records. To get one, build a data-free package with `sh deploy/make-package.sh --no-data` (writes `dist/archimaid-deploy-empty-<date>.tar.gz`, not sensitive), or run `deploy.sh` from a checkout without `deploy/data/`. The dump is only read when the volume is new.

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
- **If the first start failed** while loading the dump, the volume is half-initialized: fix the cause shown in the output, then run `sh deploy/deploy.sh --fresh`.
- **Changing the database password later** needs `ALTER USER archimaid PASSWORD '...'` in the database, then deleting and recreating the podman secret (`podman secret rm archimaid-db-password`, then `ARCHIMAID_DB_PASSWORD=... sh deploy/deploy.sh`).
- **Backup:** `podman exec archimaid-db pg_dump -U archimaid -d archimaid --no-owner --no-acl > backup.sql`
- **Remove everything:** `podman pod rm -f archimaid; podman volume rm archimaid-data; podman secret rm archimaid-db-password`
