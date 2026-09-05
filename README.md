# FABRIC Artifact Manager

A platform for sharing and reproducing FABRIC research artifacts. Built with Django 6.0, Django REST Framework, and drf-spectacular (OpenAPI docs). Provides both a REST API and a Bootstrap 5 web UI.

**DISCLAIMER: The code herein may not be up to date nor compliant with the most recent package and/or security notices. The frequency at which this code is reviewed and updated is based solely on the lifecycle of the project for which it was written to support, and is not actively maintained outside of that scope. Use at your own risk.**

## Table of Contents

- [Configuration](#config)
- [Deploy](#deploy)
- [Logging](#logging)
- [Web UI](#web-ui)
- [REST API](#rest-api)
- [Backup and Restore](#backup-restore)
- [References](#references)


## <a name="config"></a>Configuration

```bash
cp env.template .env
# Edit .env with appropriate values
source .env
uv sync          # creates .venv and installs dependencies
```

For Docker deployments, also configure:

```bash
cp vouch/config.template vouch/config
# Choose a compose template:
#   compose/docker-compose.yml.prod-ssl   — production with Nginx SSL
#   compose/docker-compose.yml.local-ssl  — local development with Nginx SSL
cp compose/docker-compose.yml.prod-ssl docker-compose.yml
```

See `env.template` for the full list of environment variables.

### Deployment-specific settings

Everything that varies between deployments is read from `.env`, so the tracked files stay
generic and a checkout can be brought forward with `git pull` without losing local changes.
Do not hand-edit `docker-compose.yml`, `nginx/default.conf.template` or `settings.py` for a
single environment — set these instead:

| Variable | Purpose |
| --- | --- |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts this deployment answers on. Loopback is always allowed. |
| `DJANGO_CORS_ALLOWED_ORIGINS` | Comma-separated origins permitted to call the API cross-site. |
| `HOST_ARTIFACT_STORAGE` | Host directory holding artifact bundles. |
| `HOST_ARTIFACT_BACKUPS` | Host directory holding database backups. |
| `HOST_DB_DATA` | Host directory backing the PostgreSQL data volume. |
| `HOST_METRICS_LOGS` | Host directory holding the metrics log — see [Logging](#logging). |
| `NGINX_HTTP_PORT` / `NGINX_HTTPS_PORT` | Host ports published by the Nginx container. |
| `NGINX_SSL_CERTS_DIR` | Host directory mounted read-only at `/etc/ssl`. |
| `AMGR_SSL_CERT` / `AMGR_SSL_CERT_KEY` | Certificate filenames within that directory. |
| `AMGR_HTTPS_PORT` | Public HTTPS port used in redirects and `server_name`. |
| `AMGR_CLIENT_MAX_BODY_SIZE` | Largest artifact bundle accepted on upload. |
| `USE_X_ACCEL_REDIRECT` | Delegate artifact downloads to Nginx — see [Artifact downloads](#downloads). |

`nginx/default.conf.template` is rendered at container start by the official Nginx image's
envsubst entrypoint. Only `${AMGR_*}` placeholders are substituted, so Nginx's own runtime
variables (`$host`, `$request_uri`, ...) pass through untouched.

## <a name="deploy"></a>Deploy

### Local development server

```bash
source .env
./run_server.sh --run-mode local-dev --make-migrations --load-fixtures
```

### Local with uWSGI + Nginx + SSL

```bash
source .env
UWSGI_UID=$(id -u) UWSGI_GID=$(id -g) ./run_server.sh --run-mode local-ssl --make-migrations --load-fixtures
```

### Docker

```bash
MAKE_MIGRATIONS=1 LOAD_FIXTURES=1 docker compose up -d
```

### <a name="downloads"></a>Artifact downloads

Bundles reach several hundred megabytes, so a download is never buffered in memory. Two
strategies, selected by `USE_X_ACCEL_REDIRECT`:

- **`false` (default)** — Django streams the file with `FileResponse`. Correct in every run
  mode, and the only option for `--run-mode local-dev`. A uWSGI worker stays occupied for the
  length of the transfer.
- **`true`** — Django authorizes the request, records the download and returns headers only,
  naming an internal Nginx location through the `X-Accel-Redirect` header. Nginx sends the
  bytes with `sendfile()`, so the worker is released immediately and byte-range and
  conditional requests are handled by Nginx. Requires the bundled Nginx with
  `HOST_ARTIFACT_STORAGE` mounted, which the supplied compose files do.

Permission checks are identical either way: the Nginx location is marked `internal`, so it
cannot be requested directly and every download still passes through
`validate_contents_download()`.

## <a name="logging"></a>Logging

Two loggers, configured by the `LOGGING` dictConfig in `artifactmgr/server/settings.py`:

- **`consoleLogger`** — operational output to stdout, where `docker compose logs django` picks
  it up. Django's own records share this stream, so `django.request` 4xx warnings and 5xx
  tracebacks are visible in production rather than swallowed.
- **`metricsLogger`** — the audit event stream. It writes to its own file and never propagates
  into stdout, so the event record stays clean enough to grep and parse.

All timestamps are UTC, in both streams, regardless of the host timezone.

Levels are set per logger in `.env`, each variable gating exactly one logger:

| Variable | Purpose |
| --- | --- |
| `DJANGO_LOG_LEVEL` | Django's own loggers. Ships as `INFO`; `DEBUG` is very chatty. |
| `ROOT_LOG_LEVEL` | Everything not covered by a more specific logger, third-party libraries included. |
| `DJANGO_DB_LOG_LEVEL` | Pinned separately so `DJANGO_LOG_LEVEL=DEBUG` cannot also switch on per-query SQL logging. |
| `CONSOLE_LOG_LEVEL` | First-party operational output — `consoleLogger` and the `artifactmgr` package logger. |
| `METRICS_LOG_LEVEL` | The metrics event stream. |
| `METRICS_LOG_FILE` | Path to the metrics log. A relative path resolves against the project root, `/code` under Docker. |
| `METRICS_LOG_MAX_BYTES` | `0` (default) uses `WatchedFileHandler` with external rotation. See the warning below. |
| `METRICS_LOG_BACKUP_COUNT` | Backup generations kept when `METRICS_LOG_MAX_BYTES > 0`. |

### The metrics log directory must exist before start

`METRICS_LOG_FILE` defaults to `./logs/metrics/metrics.log`, and under Docker the containing
directory is the bind mount named by `HOST_METRICS_LOGS` (default `./logs/metrics`, which works
out of the box for local development; point it at durable storage in production).

The handler opens the file at process startup rather than at first write. That is deliberate —
a bad path fails loudly at boot instead of silently discarding every audit record — but it means
**the directory must already exist and be writable by the uWSGI worker uid, or Django will not
start.** Under Docker, `docker-entrypoint.sh` creates it and chowns it to
`UWSGI_UID`/`UWSGI_GID` while still running as root; the chown is a warning rather than a fatal
error, because it is a no-op on Docker Desktop's virtiofs and on NFS mounts. For a deployment
whose `HOST_METRICS_LOGS` lives outside the checkout, pre-create the host directory and chown it
to the same uid before the first `docker compose up`.

### Rotation

Rotation is external. Install the supplied logrotate fragment, editing the path and the
`create` uid/gid to match this deployment's `.env`:

```bash
sudo cp logrotate/artifact-manager-metrics /etc/logrotate.d/artifact-manager-metrics
sudo logrotate -d /etc/logrotate.d/artifact-manager-metrics   # dry run, verify the paths
```

No signal or restart is needed afterwards: `WatchedFileHandler` notices the inode change and
reopens the file on its own. The fragment deliberately does not use `copytruncate`, which would
keep the inode and lose every record written between the copy and the truncate.

Setting `METRICS_LOG_MAX_BYTES` above `0` switches to an in-process `RotatingFileHandler`
instead. That is **local development only, and only for a single process**: `artifactmgr.ini`
runs four uWSGI workers with no `lazy-apps`, so all four inherit one file description, all four
see the same offset, and they stampede the rollover — destroying backup generations and losing
exactly the records an audit is later asked to produce.

Container stdout is capped by the compose `logging:` block on the `django` service (10 MB per
file, 5 files) so that raising `DJANGO_LOG_LEVEL` to `DEBUG` cannot fill the host disk.

## <a name="web-ui"></a>Web UI

The web UI provides the following pages:

| Page | URL | Description |
|------|-----|-------------|
| Artifacts | `/artifacts/` | Paginated list of all artifacts with search by title, tag, or project name |
| Artifacts by Author | `/artifacts/authors/` | Authors table with per-author artifact counts |
| Author Detail | `/artifacts/authors/<uuid>` | Paginated artifacts by a specific author with search by title, tag, or project name |
| Artifacts by Project | `/artifacts/projects/` | Projects table with per-project artifact counts and search |
| Project Detail | `/artifacts/projects/<uuid>` | Paginated artifacts for a specific FABRIC project with search by title, tag, or project name |
| Artifact Detail | `/artifacts/<uuid>` | Artifact metadata, versions, and file management |
| Create Artifact | `/artifacts/create/` | Form to create a new artifact (authenticated users) |
| Update Artifact | `/artifacts/<uuid>/update` | Form to edit an artifact (authors only) |

All list views enforce visibility-based authorization:

- **Public** artifacts are visible to everyone
- **Project** artifacts are visible to project members and authors
- **Author** artifacts are visible only to their authors

## <a name="rest-api"></a>REST API

Interactive API documentation is available at:

- `/api/swagger/` — Swagger UI
- `/api/redoc/` — ReDoc UI
- `/api/schema/` — OpenAPI 3 schema (JSON)

### Artifact endpoints

| Endpoint | Query Parameters | Description |
|----------|-----------------|-------------|
| `GET /api/artifacts` | `search`, `page` | List all visible artifacts with search by title, tag, or project name |
| `POST /api/artifacts` | | Create a new artifact |
| `GET /api/artifacts/{uuid}` | | Retrieve a specific artifact |
| `PUT /api/artifacts/{uuid}` | | Update a specific artifact |
| `PATCH /api/artifacts/{uuid}` | | Partially update a specific artifact |
| `DELETE /api/artifacts/{uuid}` | | Delete a specific artifact |
| `GET /api/artifacts/by-author/{uuid}` | `search`, `page` | List artifacts by a specific author with search by title, tag, or project name |
| `GET /api/artifacts/by-project/{uuid}` | `search`, `page` | List artifacts for a specific project with search by title, tag, or project name |

### Other endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/authors` | List all artifact authors |
| `GET /api/authors/{uuid}` | Retrieve a specific author |
| `GET /api/contents` | List artifact versions/content |
| `GET /api/contents/{uuid}` | Retrieve a specific version |
| `GET /api/contents/download/{urn}` | Download an artifact version by URN |
| `GET /api/meta/tags` | List all artifact tags |

All list endpoints support paginated results and enforce visibility-based authorization.

## <a name="backup-restore"></a>Backup and Restore

The `dumpdata.sh` script creates a timestamped backup under `./backups/` containing:

- Django JSON fixtures for each app (`apiuser`, `artifacts`) with `--natural-foreign --natural-primary` for portability
- A copy of the artifact storage directory (uploaded `.tgz` files)
- A copy of the media directory (if present)
- A `manifest.json` with timestamp, app list, and Django version

A `./backups/latest` symlink always points to the most recent backup. Fixtures are also copied to `./dumpdata/` for use with `--load-fixtures`.

### Backup

Local:

```bash
source .env
uv run ./dumpdata.sh
```

Preview commands without writing anything:

```bash
source .env
uv run ./dumpdata.sh --dry-run
```

Docker:

```bash
docker exec amgr-django /bin/bash -c "source .env; uv run ./dumpdata.sh"
docker cp amgr-django:/code/dumpdata/. dumpdata/
```

### Restore

Local:

```bash
cp dumpdata/apiuser.json artifactmgr/apps/apiuser/fixtures/
cp dumpdata/artifacts.json artifactmgr/apps/artifacts/fixtures/
# first run, make migrations, load fixtures
UWSGI_UID=$(id -u) UWSGI_GID=$(id -g) ./run_server.sh --run-mode local-ssl --load-fixtures --make-migrations
# subsequent runs, no need to load fixtures
UWSGI_UID=$(id -u) UWSGI_GID=$(id -g) ./run_server.sh --run-mode local-ssl --make-migrations
```

Docker:

```bash
cp dumpdata/apiuser.json artifactmgr/apps/apiuser/fixtures/
cp dumpdata/artifacts.json artifactmgr/apps/artifacts/fixtures/
docker compose build
MAKE_MIGRATIONS=1 LOAD_FIXTURES=1 docker compose up -d
```

## <a name="references"></a>References
