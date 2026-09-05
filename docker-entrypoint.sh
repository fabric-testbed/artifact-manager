#!/usr/bin/env bash
set -e

source .env
uv sync

# The metrics handler is opened at Django startup (delay=False), so the directory has to exist
# and be writable by the uWSGI worker before run_server.sh runs - a missing or root-owned
# directory aborts the boot. Do it here, while still root. Both steps are guarded: `set -e` is
# on, and chown is a no-op-or-error on Docker Desktop's virtiofs and on NFS mounts, so a warning
# has to be enough or macOS developers cannot start the stack.
METRICS_LOG_DIR="$(dirname "${METRICS_LOG_FILE:-./logs/metrics/metrics.log}")"
mkdir -p "${METRICS_LOG_DIR}" || echo "WARNING: could not create ${METRICS_LOG_DIR} - Django startup will fail if it does not already exist"
chown "${UWSGI_UID:-1000}:${UWSGI_GID:-1000}" "${METRICS_LOG_DIR}" || echo "WARNING: could not chown ${METRICS_LOG_DIR} to ${UWSGI_UID:-1000}:${UWSGI_GID:-1000} - expected on virtiofs/NFS mounts, verify the uWSGI worker can write there"

until [ "$(pg_isready -h database -q)"$? -eq 0 ]; do
  >&2 echo "Postgres is unavailable - sleeping"
  sleep 1
done

>&2 echo "Postgres is up - continuing"

if [ "${LOAD_FIXTURES}" -eq 1 ] && [ "${MAKE_MIGRATIONS}" -eq 1 ]; then
    uv run ./run_server.sh --run-mode docker --load-fixtures --make-migrations
elif [ "${LOAD_FIXTURES}" -eq 1 ]; then
    uv run ./run_server.sh --run-mode docker --load-fixtures
elif [ "${MAKE_MIGRATIONS}" -eq 1 ]; then
    uv run ./run_server.sh --run-mode docker --make-migrations
else
    uv run ./run_server.sh --run-mode docker
fi

exec "$@"
