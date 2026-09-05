#!/usr/bin/env bash
set -e

source .env
uv sync

# The metrics handler is opened at Django startup (delay=False), so the log file has to exist
# and be writable by the uWSGI worker before run_server.sh runs - a missing directory or a file
# the worker cannot append to aborts the boot. Do it here, while still root.
#
# The file has to be created here, not just the directory. run_server.sh below runs its
# management commands as root, and every one of them imports settings.py, which opens the
# handler - so root gets there first and creates metrics.log root-owned 0644. uWSGI then drops
# to UWSGI_UID, dictConfig reopens the file for append, and the worker takes
# `PermissionError: [Errno 13]`, which surfaces as `Unable to configure handler 'metrics'` and
# no app. Creating it here means the root-run commands write to an already-correctly-owned file.
#
# All three steps are guarded: `set -e` is on, and chown is a no-op-or-error on Docker Desktop's
# virtiofs and on NFS mounts, so a warning has to be enough or macOS developers cannot start the
# stack.
METRICS_LOG_PATH="${METRICS_LOG_FILE:-./logs/metrics/metrics.log}"
METRICS_LOG_DIR="$(dirname "${METRICS_LOG_PATH}")"
METRICS_LOG_OWNER="${UWSGI_UID:-1000}:${UWSGI_GID:-1000}"
mkdir -p "${METRICS_LOG_DIR}" || echo "WARNING: could not create ${METRICS_LOG_DIR} - Django startup will fail if it does not already exist"
touch "${METRICS_LOG_PATH}" || echo "WARNING: could not create ${METRICS_LOG_PATH} - Django startup will fail if the uWSGI worker cannot create it either"
chown "${METRICS_LOG_OWNER}" "${METRICS_LOG_DIR}" "${METRICS_LOG_PATH}" || echo "WARNING: could not chown ${METRICS_LOG_DIR} and ${METRICS_LOG_PATH} to ${METRICS_LOG_OWNER} - expected on virtiofs/NFS mounts, verify the uWSGI worker can write there"

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
