#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="icu-alert-system"
CURRENT_DIR="dist/${PROJECT_NAME}-ubuntu2004-gpu"
DELTA_ROOT="dist/delta"
BASE=""
VERSION="$(date +%Y%m%d%H%M%S)"
INTERNAL_MAX_BYTES=$((300 * 1024 * 1024))
INTERNAL_MAX_FILES=200

usage() {
    cat <<EOF
用法: $0 --base <previous-manifest.sha256|previous-release-dir> [options]

选项:
  --current <dir>              当前完整 GPU 产物目录，默认: ${CURRENT_DIR}
  --out <dir>                  增量包输出目录，默认: ${DELTA_ROOT}
  --version <version>          增量包版本号，默认: 当前时间戳
  --internal-max-mb <mb>       _internal 变更大小阈值，默认: 300
  --internal-max-files <num>   _internal 变更文件数阈值，默认: 200
  -h, --help                   显示帮助

示例:
  $0 --base previous-manifest.sha256
  $0 --base /opt/icu-alert-system-ubuntu2004-gpu
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --base)
            BASE="${2:-}"; shift 2 ;;
        --current)
            CURRENT_DIR="${2:-}"; shift 2 ;;
        --out)
            DELTA_ROOT="${2:-}"; shift 2 ;;
        --version)
            VERSION="${2:-}"; shift 2 ;;
        --internal-max-mb)
            INTERNAL_MAX_BYTES=$(( ${2:-300} * 1024 * 1024 )); shift 2 ;;
        --internal-max-files)
            INTERNAL_MAX_FILES="${2:-200}"; shift 2 ;;
        -h|--help)
            usage; exit 0 ;;
        *)
            echo "未知参数: $1" >&2; usage; exit 2 ;;
    esac
done

if [ -z "${BASE}" ]; then
    echo "错误: 必须指定 --base <manifest|dir>" >&2
    usage
    exit 2
fi
if [ ! -d "${CURRENT_DIR}" ]; then
    echo "错误: 当前产物目录不存在: ${CURRENT_DIR}" >&2
    echo "请先执行 ./build-gpu.sh" >&2
    exit 1
fi

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "${TMP_DIR}"; }
trap cleanup EXIT

CURRENT_MANIFEST="${TMP_DIR}/current.manifest"
BASE_MANIFEST="${TMP_DIR}/base.manifest"
CHANGED_LIST="${TMP_DIR}/changed-files.txt"
REMOVED_LIST="${TMP_DIR}/removed-files.txt"
PAYLOAD_DIR="${TMP_DIR}/payload"

make_manifest() {
    local dir="$1"
    local label="${2:-manifest}"
    (cd "$dir" && \
        mapfile -t files < <(find . -type f \
            ! -name 'manifest.sha256' \
            ! -path './.env' \
            ! -name '*.pid' \
            ! -name '*.log' \
            ! -path './backups/*' \
            ! -path './.delta-backups/*' \
            -print | sort) && \
        total="${#files[@]}" && \
        echo ">>> ${label}: 发现 ${total} 个文件，开始计算 SHA256..." >&2 && \
        index=0 && \
        for file in "${files[@]}"; do
            index=$((index + 1))
            if [ "${index}" -eq 1 ] || [ $((index % 200)) -eq 0 ] || [ "${index}" -eq "${total}" ]; then
                echo ">>> ${label}: ${index}/${total} ${file#./}" >&2
            fi
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

normalize_manifest() {
    awk '{
        hash=$1
        $1=""
        sub(/^  /, "")
        sub(/^\.\//, "")
        if (hash != "" && $0 != "") print hash "\t" $0
    }' "$1" | sort -k2,2
}

if [ -d "${BASE}" ]; then
    make_manifest "${BASE}" "base manifest" > "${BASE_MANIFEST}.raw"
elif [ -f "${BASE}" ]; then
    echo ">>> 使用 base manifest 文件: ${BASE}"
    cp "${BASE}" "${BASE_MANIFEST}.raw"
else
    echo "错误: base 不存在: ${BASE}" >&2
    exit 1
fi

make_manifest "${CURRENT_DIR}" "current manifest" > "${CURRENT_MANIFEST}.raw"
echo ">>> 规范化 manifest..."
normalize_manifest "${BASE_MANIFEST}.raw" > "${BASE_MANIFEST}"
normalize_manifest "${CURRENT_MANIFEST}.raw" > "${CURRENT_MANIFEST}"

echo ">>> 计算变更文件列表..."
awk -F '\t' '
    NR == FNR { base[$2] = $1; next }
    !($2 in base) || base[$2] != $1 { print $2 }
' "${BASE_MANIFEST}" "${CURRENT_MANIFEST}" > "${CHANGED_LIST}"

echo ">>> 计算删除文件列表..."
awk -F '\t' '
    NR == FNR { cur[$2] = 1; next }
    !($2 in cur) { print $2 }
' "${CURRENT_MANIFEST}" "${BASE_MANIFEST}" > "${REMOVED_LIST}"

validate_file_list "${CHANGED_LIST}"
validate_file_list "${REMOVED_LIST}"

INTERNAL_CHANGED_FILES=$(grep -c '^_internal/' "${CHANGED_LIST}" || true)
INTERNAL_CHANGED_BYTES=0
if [ "${INTERNAL_CHANGED_FILES}" -gt 0 ]; then
    while IFS= read -r file; do
        [ -f "${CURRENT_DIR}/${file}" ] || continue
        size=$(wc -c < "${CURRENT_DIR}/${file}" | tr -d ' ')
        INTERNAL_CHANGED_BYTES=$((INTERNAL_CHANGED_BYTES + size))
    done < <(grep '^_internal/' "${CHANGED_LIST}" || true)
fi

if [ "${INTERNAL_CHANGED_FILES}" -gt "${INTERNAL_MAX_FILES}" ] || [ "${INTERNAL_CHANGED_BYTES}" -gt "${INTERNAL_MAX_BYTES}" ]; then
    echo "错误: _internal 变化过大，建议发布完整 GPU 包。" >&2
    echo "  _internal 变化文件数: ${INTERNAL_CHANGED_FILES} (阈值 ${INTERNAL_MAX_FILES})" >&2
    echo "  _internal 变化大小: $((INTERNAL_CHANGED_BYTES / 1024 / 1024)) MB (阈值 $((INTERNAL_MAX_BYTES / 1024 / 1024)) MB)" >&2
    exit 3
fi

mkdir -p "${PAYLOAD_DIR}/files" "${DELTA_ROOT}"

CHANGED_TOTAL=$(wc -l < "${CHANGED_LIST}" | tr -d ' ')
CHANGED_INDEX=0
echo ">>> 复制变更文件到增量包: ${CHANGED_TOTAL} 个"
while IFS= read -r file; do
    [ -n "${file}" ] || continue
    [ -f "${CURRENT_DIR}/${file}" ] || continue
    CHANGED_INDEX=$((CHANGED_INDEX + 1))
    if [ "${CHANGED_INDEX}" -eq 1 ] || [ $((CHANGED_INDEX % 100)) -eq 0 ] || [ "${CHANGED_INDEX}" -eq "${CHANGED_TOTAL}" ]; then
        echo ">>> 复制进度: ${CHANGED_INDEX}/${CHANGED_TOTAL} ${file}"
    fi
    mkdir -p "${PAYLOAD_DIR}/files/$(dirname "$file")"
    cp -p "${CURRENT_DIR}/${file}" "${PAYLOAD_DIR}/files/${file}"
done < "${CHANGED_LIST}"

cp "${CURRENT_MANIFEST}.raw" "${PAYLOAD_DIR}/manifest.sha256"
cp "${CHANGED_LIST}" "${PAYLOAD_DIR}/changed-files.txt"
cp "${REMOVED_LIST}" "${PAYLOAD_DIR}/removed-files.txt"
cp "apply-gpu-delta.sh" "${PAYLOAD_DIR}/apply-gpu-delta.sh"
chmod +x "${PAYLOAD_DIR}/apply-gpu-delta.sh"

cat > "${PAYLOAD_DIR}/delta-info.txt" <<EOF
project=${PROJECT_NAME}
target=ubuntu2004-gpu
version=${VERSION}
created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
changed_files=$(wc -l < "${CHANGED_LIST}" | tr -d ' ')
removed_files=$(wc -l < "${REMOVED_LIST}" | tr -d ' ')
internal_changed_files=${INTERNAL_CHANGED_FILES}
internal_changed_bytes=${INTERNAL_CHANGED_BYTES}
EOF

ARCHIVE_NAME="${PROJECT_NAME}-gpu-delta-${VERSION}.tar.gz"
ARCHIVE_PATH="${DELTA_ROOT}/${ARCHIVE_NAME}"
echo ">>> 压缩增量包: ${ARCHIVE_PATH}"
tar -czf "${ARCHIVE_PATH}" -C "${PAYLOAD_DIR}" .

echo "============================================"
echo "  GPU 增量包生成完成"
echo "============================================"
echo "  当前产物:      ${CURRENT_DIR}"
echo "  Base:          ${BASE}"
echo "  增量包:        ${ARCHIVE_PATH}"
echo "  增量包大小:    $(du -sh "${ARCHIVE_PATH}" | awk '{print $1}')"
echo "  变更文件数:    $(wc -l < "${CHANGED_LIST}" | tr -d ' ')"
echo "  删除文件数:    $(wc -l < "${REMOVED_LIST}" | tr -d ' ')"
echo "  _internal变更: ${INTERNAL_CHANGED_FILES} 文件, $((INTERNAL_CHANGED_BYTES / 1024 / 1024)) MB"
echo ""
echo "服务器应用:"
echo "  mkdir -p /tmp/icu-delta && tar xzf ${ARCHIVE_NAME} -C /tmp/icu-delta"
echo "  /tmp/icu-delta/apply-gpu-delta.sh /opt/${PROJECT_NAME}-ubuntu2004-gpu"
echo "============================================"
