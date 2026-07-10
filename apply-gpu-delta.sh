#!/usr/bin/env bash
set -euo pipefail

DEFAULT_TARGET="/opt/icu-alert-system-ubuntu2004-gpu"
TARGET_DIR="${1:-${DEFAULT_TARGET}}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FILES_DIR="${SCRIPT_DIR}/files"
MANIFEST_FILE="${SCRIPT_DIR}/manifest.sha256"
CHANGED_LIST="${SCRIPT_DIR}/changed-files.txt"
REMOVED_LIST="${SCRIPT_DIR}/removed-files.txt"
KEEP_BACKUPS="${KEEP_BACKUPS:-3}"

fail() {
    echo "错误: $*" >&2
    exit 1
}

make_manifest() {
    local dir="$1"
    (cd "$dir" && \
        find . -type f \
            ! -name 'manifest.sha256' \
            ! -path './.env' \
            ! -name '*.pid' \
            ! -name '*.log' \
            ! -path './backups/*' \
            ! -path './.delta-backups/*' \
            -print | sort | while IFS= read -r file; do
                sha256sum "$file" | sed 's#  \./#  #'
            done)
}

validate_file_list() {
    local list="$1"
    awk '
        $0 == "" { next }
        $0 ~ /^\// || $0 ~ /(^|\/)\.\.(\/|$)/ {
            print "非法路径: " $0 > "/dev/stderr"
            bad = 1
        }
        END { exit bad ? 1 : 0 }
    ' "$list"
}

[ -d "${TARGET_DIR}" ] || fail "部署目录不存在: ${TARGET_DIR}"
[ -d "${FILES_DIR}" ] || fail "增量包缺少 files/ 目录: ${FILES_DIR}"
[ -f "${MANIFEST_FILE}" ] || fail "增量包缺少 manifest.sha256"
[ -f "${CHANGED_LIST}" ] || fail "增量包缺少 changed-files.txt"
[ -f "${REMOVED_LIST}" ] || fail "增量包缺少 removed-files.txt"
validate_file_list "${CHANGED_LIST}" || fail "changed-files.txt 包含非法路径"
validate_file_list "${REMOVED_LIST}" || fail "removed-files.txt 包含非法路径"

BACKUP_ROOT="${TARGET_DIR}/.delta-backups"
BACKUP_DIR="${BACKUP_ROOT}/$(date +%Y%m%d%H%M%S)"
mkdir -p "${BACKUP_DIR}/files"

echo "============================================"
echo "  应用 ICU GPU 增量包"
echo "============================================"
echo "  部署目录: ${TARGET_DIR}"
echo "  增量目录: ${SCRIPT_DIR}"
echo "  备份目录: ${BACKUP_DIR}"

cd "${TARGET_DIR}"

if [ -x "./run.sh" ]; then
    ./run.sh stop || true
fi

[ -f manifest.sha256 ] && cp -p manifest.sha256 "${BACKUP_DIR}/manifest.sha256.previous"
cp "${CHANGED_LIST}" "${BACKUP_DIR}/changed-files.txt"
cp "${REMOVED_LIST}" "${BACKUP_DIR}/removed-files.txt"

while IFS= read -r file; do
    [ -n "${file}" ] || continue
    if [ -e "${file}" ]; then
        mkdir -p "${BACKUP_DIR}/files/$(dirname "$file")"
        cp -a "${file}" "${BACKUP_DIR}/files/${file}"
    fi
done < "${CHANGED_LIST}"

while IFS= read -r file; do
    [ -n "${file}" ] || continue
    if [ -e "${file}" ]; then
        mkdir -p "${BACKUP_DIR}/files/$(dirname "$file")"
        cp -a "${file}" "${BACKUP_DIR}/files/${file}"
        rm -rf "${file}"
    fi
done < "${REMOVED_LIST}"

while IFS= read -r file; do
    [ -n "${file}" ] || continue
    [ -f "${FILES_DIR}/${file}" ] || fail "增量包缺少变更文件: ${file}"
    mkdir -p "$(dirname "$file")"
    cp -p "${FILES_DIR}/${file}" "${file}"
done < "${CHANGED_LIST}"

cp "${MANIFEST_FILE}" manifest.sha256
chmod +x icu-alert-system run.sh 2>/dev/null || true

VERIFY_FILE="${BACKUP_DIR}/manifest.sha256.actual"
make_manifest "${TARGET_DIR}" > "${VERIFY_FILE}"
if ! diff -u manifest.sha256 "${VERIFY_FILE}" > "${BACKUP_DIR}/manifest.diff"; then
    echo "错误: manifest 校验失败，开始回滚..." >&2
    while IFS= read -r file; do
        [ -n "${file}" ] || continue
        rm -rf "${file}"
    done < "${CHANGED_LIST}"
    while IFS= read -r file; do
        [ -n "${file}" ] || continue
        [ -e "${BACKUP_DIR}/files/${file}" ] || continue
        mkdir -p "$(dirname "$file")"
        cp -a "${BACKUP_DIR}/files/${file}" "${file}"
    done < <(find "${BACKUP_DIR}/files" -type f | sed "s#^${BACKUP_DIR}/files/##" | sort)
    [ -f "${BACKUP_DIR}/manifest.sha256.previous" ] && cp -p "${BACKUP_DIR}/manifest.sha256.previous" manifest.sha256
    echo "manifest 差异: ${BACKUP_DIR}/manifest.diff" >&2
    exit 1
fi

if [ -x "./run.sh" ]; then
    ./run.sh start-bg
fi

if [ -d "${BACKUP_ROOT}" ]; then
    BACKUP_COUNT=$(find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
    if [ "${BACKUP_COUNT}" -gt "${KEEP_BACKUPS}" ]; then
        REMOVE_COUNT=$((BACKUP_COUNT - KEEP_BACKUPS))
        find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d | sort | head -n "${REMOVE_COUNT}" | xargs -r rm -rf
    fi
fi

echo "============================================"
echo "  增量更新完成"
echo "============================================"
echo "  变更文件数: $(wc -l < "${CHANGED_LIST}" | tr -d ' ')"
echo "  删除文件数: $(wc -l < "${REMOVED_LIST}" | tr -d ' ')"
echo "  备份目录:   ${BACKUP_DIR}"
echo "============================================"
