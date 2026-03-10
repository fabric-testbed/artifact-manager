# FABRIC Artifact Manager

A platform for sharing and reproducing FABRIC research artifacts. Built with Django 6.0, Django REST Framework, and drf-spectacular (OpenAPI docs). Provides both a REST API and a Bootstrap 5 web UI.

**DISCLAIMER: The code herein may not be up to date nor compliant with the most recent package and/or security notices. The frequency at which this code is reviewed and updated is based solely on the lifecycle of the project for which it was written to support, and is not actively maintained outside of that scope. Use at your own risk.**

## Table of Contents

- [Configuration](#config)
- [Deploy](#deploy)
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
vim nginx/default.conf
```

See `env.template` for the full list of environment variables.

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
