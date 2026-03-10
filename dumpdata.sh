#!/usr/bin/env bash
set -uo pipefail

# ---------------------------------------------------------------------------
# dumpdata.sh — Back up the Artifact Manager database and uploaded files
#
# Creates a timestamped backup directory under ./backups/ containing:
#   - Django JSON fixtures for each app (apiuser, artifacts)
#   - A copy of the artifact storage directory (uploaded .tgz files)
#   - A copy of the media directory (if it exists and is non-empty)
#
# Usage:
#   source .env && ./dumpdata.sh            # full backup
#   source .env && ./dumpdata.sh --dry-run  # preview commands only
#
# The latest backup is also symlinked at ./backups/latest for convenience.
# ---------------------------------------------------------------------------

# Resolve paths relative to this script's location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGE_PY="${SCRIPT_DIR}/manage.py"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
fi

TIMESTAMP=$(date +%Y%m%dT%H%M%S)
BACKUP_DIR="${SCRIPT_DIR}/backups/${TIMESTAMP}"
DUMPDATA_DIR="${SCRIPT_DIR}/dumpdata"

# App order matters — apiuser first (referenced by artifacts via FK)
APPS_LIST=(
    "apiuser"
    "artifacts"
)

# Common dumpdata flags
#   --natural-foreign : use natural keys for FK references so fixtures are
#                       portable across database instances
#   --natural-primary : use natural keys for primary keys where defined
DUMP_FLAGS=(--indent 2 --natural-foreign --natural-primary)

# Resolve storage/media paths from environment (fall back to defaults)
ARTIFACT_STORAGE="${FABRIC_ARTIFACT_STORAGE_DIR:-${SCRIPT_DIR}/artifact_storage}"
MEDIA_DIR="${SCRIPT_DIR}/media"

ERRORS=0

# ── Create backup directory ───────────────────────────────────────────────
echo "==> Creating backup directory: ${BACKUP_DIR}"
if [[ "${DRY_RUN}" == false ]]; then
    mkdir -p "${BACKUP_DIR}/db"
fi

# ── Dump Django app data ──────────────────────────────────────────────────
echo "==> Dumping database fixtures ..."
for app in "${APPS_LIST[@]}"; do
    outfile="${BACKUP_DIR}/db/${app}.json"
    CMD="python3 ${MANAGE_PY} dumpdata ${app} ${DUMP_FLAGS[*]} --output ${outfile}"
    echo "    >>> ${CMD}"

    if [[ "${DRY_RUN}" == true ]]; then
        continue
    fi

    if ! python3 "${MANAGE_PY}" dumpdata "${app}" "${DUMP_FLAGS[@]}" --output "${outfile}"; then
        echo "    ERROR: dumpdata failed for app '${app}'" >&2
        ERRORS=$((ERRORS + 1))
        continue
    fi

    # Validate: file must exist, be non-empty, and parse as valid JSON
    if [[ ! -s "${outfile}" ]]; then
        echo "    ERROR: ${outfile} is missing or empty" >&2
        ERRORS=$((ERRORS + 1))
        continue
    fi
    if ! python3 -c "import json, sys; json.load(open(sys.argv[1]))" "${outfile}" 2>/dev/null; then
        echo "    ERROR: ${outfile} is not valid JSON" >&2
        ERRORS=$((ERRORS + 1))
        continue
    fi
    echo "    OK: ${outfile} ($(wc -c < "${outfile}" | tr -d ' ') bytes)"
done

# ── Also write a copy to ./dumpdata/ for fixture loading ──────────────────
if [[ "${DRY_RUN}" == false ]]; then
    echo "==> Copying fixtures to ${DUMPDATA_DIR}/ (for --load-fixtures) ..."
    mkdir -p "${DUMPDATA_DIR}"
    for app in "${APPS_LIST[@]}"; do
        src="${BACKUP_DIR}/db/${app}.json"
        if [[ -f "${src}" ]]; then
            cp "${src}" "${DUMPDATA_DIR}/${app}.json"
        fi
    done
fi

# ── Back up artifact storage files ────────────────────────────────────────
if [[ -d "${ARTIFACT_STORAGE}" ]] && [[ -n "$(ls -A "${ARTIFACT_STORAGE}" 2>/dev/null)" ]]; then
    echo "==> Copying artifact storage: ${ARTIFACT_STORAGE} ..."
    if [[ "${DRY_RUN}" == false ]]; then
        cp -a "${ARTIFACT_STORAGE}" "${BACKUP_DIR}/artifact_storage"
        FILE_COUNT=$(find "${BACKUP_DIR}/artifact_storage" -type f | wc -l | tr -d ' ')
        echo "    OK: ${FILE_COUNT} file(s) copied"
    else
        FILE_COUNT=$(find "${ARTIFACT_STORAGE}" -type f | wc -l | tr -d ' ')
        echo "    (would copy ${FILE_COUNT} file(s))"
    fi
else
    echo "==> Skipping artifact storage (${ARTIFACT_STORAGE} is empty or missing)"
fi

# ── Back up media directory ───────────────────────────────────────────────
if [[ -d "${MEDIA_DIR}" ]] && [[ -n "$(ls -A "${MEDIA_DIR}" 2>/dev/null)" ]]; then
    echo "==> Copying media directory: ${MEDIA_DIR} ..."
    if [[ "${DRY_RUN}" == false ]]; then
        cp -a "${MEDIA_DIR}" "${BACKUP_DIR}/media"
        FILE_COUNT=$(find "${BACKUP_DIR}/media" -type f | wc -l | tr -d ' ')
        echo "    OK: ${FILE_COUNT} file(s) copied"
    else
        FILE_COUNT=$(find "${MEDIA_DIR}" -type f | wc -l | tr -d ' ')
        echo "    (would copy ${FILE_COUNT} file(s))"
    fi
else
    echo "==> Skipping media directory (${MEDIA_DIR} is empty or missing)"
fi

# ── Write manifest ────────────────────────────────────────────────────────
if [[ "${DRY_RUN}" == false ]]; then
    DJANGO_VERSION="$(python3 "${MANAGE_PY}" version 2>/dev/null || echo 'unknown')"
    cat > "${BACKUP_DIR}/manifest.json" <<MANIFEST
{
  "dumped_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "apps": [$(printf '"%s", ' "${APPS_LIST[@]}" | sed 's/, $//')],
  "django_version": "${DJANGO_VERSION}",
  "artifact_storage": "${ARTIFACT_STORAGE}",
  "errors": ${ERRORS}
}
MANIFEST
    echo "==> Manifest written to ${BACKUP_DIR}/manifest.json"
fi

# ── Update "latest" symlink ───────────────────────────────────────────────
if [[ "${DRY_RUN}" == false ]]; then
    ln -sfn "${TIMESTAMP}" "${SCRIPT_DIR}/backups/latest"
fi

# ── Summary ───────────────────────────────────────────────────────────────
if [[ "${DRY_RUN}" == false ]]; then
    TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" | cut -f1)
    echo ""
    echo "==> Backup complete: ${BACKUP_DIR} (${TOTAL_SIZE})"
    echo "    Symlink: ./backups/latest -> ${TIMESTAMP}"
else
    echo ""
    echo "==> Dry run complete. No files were written."
fi

if [[ ${ERRORS} -gt 0 ]]; then
    echo ""
    echo "WARNING: ${ERRORS} app(s) had errors during export." >&2
    exit 1
fi

exit 0
