#!/usr/bin/env bash
# deploy-release.sh - the standard procedure for moving a host to a published release.
#
#   sudo bash scripts/deploy-release.sh <tag> <fqdn> [deploy-dir]
#   ssh <host> 'sudo bash -s -- v1.16.2 artifacts.example.org' < scripts/deploy-release.sh
#
# The second form deploys a release from a checkout that does not have this script yet.
#
# Steps:
#   1. back up .env, the git revision and a pg_dump to
#      /home/nrig-service/amgr-deploy-backups/<UTC timestamp>-pre-<tag>/
#   2. git pull --ff-only origin main as the checkout owner; the result must be <tag>
#   3. `docker compose config` as the gate: a .env missing a variable the release needs fails
#      here, before anything is restarted. Patch .env first when the CHANGELOG says so.
#   4. pull the nginx image, then force-recreate BOTH django and nginx. Every deploy does this:
#      `up -d` alone leaves nginx running on its old image and its old rendered template, and
#      uWSGI does not reload code from the bind mount on its own.
#   5. health checks through nginx: robots.txt 200, footer shows the release, `nginx -t`, and no
#      new [ERROR] lines from django. On failure the previous revision and nginx image are
#      restored and both services recreated again.
set -uo pipefail

TAG=${1:?usage: deploy-release.sh <tag> <fqdn> [deploy-dir]}
FQDN=${2:?usage: deploy-release.sh <tag> <fqdn> [deploy-dir]}
DIR=${3:-/home/nrig-service/artifact-manager}
OWNER=$(stat -c %U "${DIR}")
BACKUP_ROOT=${DEPLOY_BACKUP_ROOT:-/home/nrig-service/amgr-deploy-backups}
WAIT_SECONDS=${DEPLOY_WAIT_SECONDS:-300}

[ "$(id -u)" = 0 ] || { echo "run as root (sudo)" >&2; exit 1; }
cd "${DIR}" || exit 1
set -a; . ./.env; set +a
HTTPS_PORT=${NGINX_HTTPS_PORT:-8443}

g() { sudo -iu "${OWNER}" git -C "${DIR}" "$@"; }
c() { curl -k -sS --max-time 20 --resolve "${FQDN}:${HTTPS_PORT}:127.0.0.1" "$@"; }
log() { echo "[$(date -u +%H:%M:%S)] $*"; }

# Also starts, or recreates on a config change, anything else in the stack. Not --no-deps: after a
# --no-deps recreate, every later plain `docker compose up -d` recreates django yet again.
recreate() {
    docker compose up -d --force-recreate django nginx </dev/null
}

healthy() {
    local version=$1 since=$2 deadline=$((SECONDS + WAIT_SECONDS)) code
    until [ "$(c -o /dev/null -w '%{http_code}' "https://${FQDN}:${HTTPS_PORT}/robots.txt" 2>/dev/null)" = 200 ]; do
        [ "${SECONDS}" -ge "${deadline}" ] && { log "FAIL robots.txt not 200 within ${WAIT_SECONDS}s"; return 1; }
        sleep 5
    done
    log "ok   robots.txt 200"
    docker compose exec -T nginx nginx -t </dev/null >/dev/null 2>&1 \
        && log "ok   nginx -t" || { log "FAIL nginx -t"; return 1; }
    code=$(c -o /tmp/deploy-footer.html -w '%{http_code}' "https://${FQDN}:${HTTPS_PORT}/artifacts/")
    if [ "${code}" = 200 ] && grep -qF "v${version}" /tmp/deploy-footer.html; then
        log "ok   /artifacts/ 200, footer v${version}"
    else
        log "FAIL /artifacts/ status ${code} or footer is not v${version}"; return 1
    fi
    local errors
    errors=$(docker compose logs --since "${since}" django 2>/dev/null | grep -c '\[ERROR\]')
    [ "${errors}" = 0 ] && log "ok   django: no [ERROR] since recreate" \
        || { log "FAIL django: ${errors} [ERROR] lines since recreate"; return 1; }
}

# --- 1. backup -------------------------------------------------------------------------------
STAMP=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${BACKUP_ROOT}/${STAMP}-pre-${TAG}"
mkdir -p "${BACKUP}" && cp -p .env "${BACKUP}/.env" || exit 1
PREV_REV=$(g rev-parse HEAD)
echo "${PREV_REV}" > "${BACKUP}/git-rev"
PREV_VERSION=$(cat VERSION)
PREV_NGINX_IMAGE=$(docker inspect -f '{{.Image}}' amgr-nginx 2>/dev/null || true)
NGINX_IMAGE=$(docker inspect -f '{{.Config.Image}}' amgr-nginx 2>/dev/null || echo nginx:1)
echo "${PREV_NGINX_IMAGE}" > "${BACKUP}/nginx-image"
docker compose exec -T database pg_dump -Fc -U "${POSTGRES_USER}" "${POSTGRES_DB}" </dev/null \
    > "${BACKUP}/database.dump" || { log "FAIL pg_dump"; exit 1; }
log "backup ${BACKUP} (v${PREV_VERSION} ${PREV_REV:0:7}, db $(du -h "${BACKUP}/database.dump" | cut -f1))"

# --- 2. pull ---------------------------------------------------------------------------------
[ -z "$(g status --porcelain --untracked-files=no)" ] || { log "FAIL tracked files are modified"; g status --short; exit 1; }
g fetch -q origin --tags || exit 1
g merge-base --is-ancestor HEAD origin/main || { log "FAIL HEAD is not an ancestor of origin/main"; exit 1; }
[ "$(g rev-parse "${TAG}^{commit}" 2>/dev/null)" = "$(g rev-parse origin/main)" ] \
    || { log "FAIL ${TAG} is not origin/main - publish the release first"; exit 1; }
g checkout -q -B main origin/main || exit 1
VERSION=$(cat VERSION)
[ "v${VERSION}" = "${TAG}" ] || { log "FAIL VERSION is ${VERSION}, want ${TAG}"; g checkout -q -B main "${PREV_REV}"; exit 1; }
log "checkout ${PREV_REV:0:7} -> $(g rev-parse --short HEAD) (v${VERSION})"

# --- 3. gate ---------------------------------------------------------------------------------
docker compose config -q || { log "FAIL docker compose config - fix .env"; g checkout -q -B main "${PREV_REV}"; exit 1; }
log "ok   docker compose config"

# --- 4. nginx image + recreate ---------------------------------------------------------------
docker compose pull -q nginx </dev/null || log "WARN nginx pull failed, keeping the local image"
log "nginx image ${NGINX_IMAGE} ${PREV_NGINX_IMAGE:7:12} -> $(docker image inspect -f '{{.Id}}' "${NGINX_IMAGE}" | cut -c8-19)"
SINCE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
recreate || log "FAIL recreate"

# --- 5. verify, roll back on failure ---------------------------------------------------------
if healthy "${VERSION}" "${SINCE}"; then
    log "deployed ${TAG} on ${FQDN}; backup ${BACKUP}"
    exit 0
fi
log "ROLLBACK to v${PREV_VERSION} ${PREV_REV:0:7}"
g checkout -q -B main "${PREV_REV}"
[ -n "${PREV_NGINX_IMAGE}" ] && docker tag "${PREV_NGINX_IMAGE}" "${NGINX_IMAGE}"
SINCE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
recreate
healthy "${PREV_VERSION}" "${SINCE}" && log "rolled back; investigate before retrying" || log "ROLLBACK ALSO FAILED - intervene by hand"
exit 1
