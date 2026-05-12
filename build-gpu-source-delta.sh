#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="icu-alert-system"
DELTA_ROOT="dist/delta"
BASE_MANIFEST=""
BASE_COMMIT=""
VERSION="$(date +%Y%m%d%H%M%S)"

usage() {
    cat <<EOF
用法: $0 --base-manifest <manifest.sha256> [options]

不运行 Docker，不运行 PyInstaller。直接基于当前源码生成 Ubuntu GPU 源码增量包。

选项:
  --base-manifest <file>   服务器当前版本的 manifest.sha256，必填
  --base-commit <commit>   上次发布的 git commit；提供后会检查是否改了必须完整打包的文件
  --out <dir>              增量包输出目录，默认: ${DELTA_ROOT}
  --version <version>      增量包版本号，默认: 当前时间戳
  -h, --help               显示帮助

示例:
  $0 --base-manifest old-manifest.sha256 --base-commit v20260512
  $0 --base-manifest old-manifest.sha256
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --base-manifest)
            BASE_MANIFEST="${2:-}"; shift 2 ;;
        --base-commit)
            BASE_COMMIT="${2:-}"; shift 2 ;;
        --out)
            DELTA_ROOT="${2:-}"; shift 2 ;;
        --version)
            VERSION="${2:-}"; shift 2 ;;
        -h|--help)
            usage; exit 0 ;;
        *)
            echo "未知参数: $1" >&2; usage; exit 2 ;;
    esac
done

if [ -z "${BASE_MANIFEST}" ] || [ ! -f "${BASE_MANIFEST}" ]; then
    echo "错误: 必须指定存在的 --base-manifest <manifest.sha256>" >&2
    usage
    exit 2
fi

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "${TMP_DIR}"; }
trap cleanup EXIT

BASE_NORM="${TMP_DIR}/base.norm"
CURRENT_MANAGED="${TMP_DIR}/current-managed.norm"
NEW_MANIFEST_NORM="${TMP_DIR}/new-manifest.norm"
NEW_MANIFEST_RAW="${TMP_DIR}/manifest.sha256"
CHANGED_LIST="${TMP_DIR}/changed-files.txt"
REMOVED_LIST="${TMP_DIR}/removed-files.txt"
PAYLOAD_DIR="${TMP_DIR}/payload"
MANAGED_PREFIXES="${TMP_DIR}/managed-prefixes.txt"

normalize_manifest() {
    awk '{
        hash=$1
        $1=""
        sub(/^  /, "")
        sub(/^\.\//, "")
        if (hash != "" && $0 != "") print hash "\t" $0
    }' "$1" | sort -k2,2
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

add_managed_file() {
    local src="$1"
    local target="$2"
    [ -f "${src}" ] || return 0
    case "${target}" in
        /*|*../*|../*) echo "非法目标路径: ${target}" >&2; exit 1 ;;
    esac
    sha256sum "${src}" | awk -v target="${target}" '{ print $1 "\t" target }' >> "${CURRENT_MANAGED}"
}

scan_tree() {
    local src_root="$1"
    local target_root="$2"
    [ -d "${src_root}" ] || return 0
    echo "${target_root}/" >> "${MANAGED_PREFIXES}"
    while IFS= read -r file; do
        rel="${file#${src_root}/}"
        case "${rel}" in
            __pycache__/*|*.pyc|*.pyo|*.log|*.pid) continue ;;
        esac
        add_managed_file "${file}" "${target_root}/${rel}"
    done < <(find "${src_root}" -type f | sort)
}

check_full_build_required() {
    [ -n "${BASE_COMMIT}" ] || return 0
    echo ">>> 检查 ${BASE_COMMIT}..HEAD 是否包含必须完整打包的变更..."
    local blocked="${TMP_DIR}/blocked.txt"
    git diff --name-only "${BASE_COMMIT}..HEAD" | awk '
        /^Dockerfile/ ||
        /^Dockerfile\.gpu-build$/ ||
        /^build-gpu\.sh$/ ||
        /^entry\.py$/ ||
        /^backend\/requirements/ ||
        /^backend\/requirements.*\.txt$/ ||
        /^frontend\/package(-lock)?\.json$/ ||
        /^package(-lock)?\.json$/ {
            print
        }
    ' > "${blocked}"
    if [ -s "${blocked}" ]; then
        echo "错误: 以下文件变更会影响 GPU 基座/依赖，不能做源码增量，请完整打包:" >&2
        sed 's/^/  - /' "${blocked}" >&2
        exit 3
    fi
}

check_full_build_required
normalize_manifest "${BASE_MANIFEST}" > "${BASE_NORM}"
: > "${CURRENT_MANAGED}"
: > "${MANAGED_PREFIXES}"

echo ">>> 扫描当前源码可增量发布文件..."
scan_tree "backend/app" "app"
[ -f "backend/config.yaml" ] && add_managed_file "backend/config.yaml" "config.yaml"
if [ -d "backend/knowledge_base" ]; then
    scan_tree "backend/knowledge_base" "knowledge_base"
fi
if [ -d "backend/static" ]; then
    scan_tree "backend/static" "static"
elif [ -d "frontend/dist" ]; then
    scan_tree "frontend/dist" "static"
else
    echo ">>> 未发现 backend/static 或 frontend/dist，本次不管理 static/ 前端产物"
fi

sort -k2,2 -o "${CURRENT_MANAGED}" "${CURRENT_MANAGED}"

echo ">>> 计算源码增量变更..."
awk -F '\t' '
    NR == FNR { base[$2] = $1; next }
    !($2 in base) || base[$2] != $1 { print $2 }
' "${BASE_NORM}" "${CURRENT_MANAGED}" > "${CHANGED_LIST}"

awk -F '\t' '
    NR == FNR { cur[$2] = 1; next }
    FILENAME == ARGV[2] { prefixes[$1] = 1; next }
    {
        managed = 0
        for (prefix in prefixes) {
            if ($2 == substr(prefix, 1, length(prefix)-1) || index($2, prefix) == 1) {
                managed = 1
                break
            }
        }
        if (managed && !($2 in cur)) print $2
    }
' "${CURRENT_MANAGED}" "${MANAGED_PREFIXES}" "${BASE_NORM}" > "${REMOVED_LIST}"

validate_file_list "${CHANGED_LIST}"
validate_file_list "${REMOVED_LIST}"

mkdir -p "${PAYLOAD_DIR}/files" "${DELTA_ROOT}"
CHANGED_TOTAL=$(wc -l < "${CHANGED_LIST}" | tr -d ' ')
echo ">>> 复制变更文件到源码增量包: ${CHANGED_TOTAL} 个"
while IFS= read -r target; do
    [ -n "${target}" ] || continue
    src=""
    case "${target}" in
        app/*) src="backend/${target}" ;;
        config.yaml) src="backend/config.yaml" ;;
        knowledge_base/*) src="backend/${target}" ;;
        static/*)
            rel="${target#static/}"
            if [ -f "backend/static/${rel}" ]; then
                src="backend/static/${rel}"
            elif [ -f "frontend/dist/${rel}" ]; then
                src="frontend/dist/${rel}"
            fi
            ;;
    esac
    [ -n "${src}" ] && [ -f "${src}" ] || { echo "错误: 找不到源文件 ${target}" >&2; exit 1; }
    mkdir -p "${PAYLOAD_DIR}/files/$(dirname "${target}")"
    cp -p "${src}" "${PAYLOAD_DIR}/files/${target}"
done < "${CHANGED_LIST}"

awk -F '\t' '
    NR == FNR { cur[$2] = $1; next }
    FILENAME == ARGV[2] { removed[$1] = 1; next }
    {
        if ($2 in removed) next
        if ($2 in cur) next
        print $1 "\t" $2
    }
    END {
        for (path in cur) print cur[path] "\t" path
    }
' "${CURRENT_MANAGED}" "${REMOVED_LIST}" "${BASE_NORM}" | sort -k2,2 > "${NEW_MANIFEST_NORM}"

awk -F '\t' '{ print $1 "  " $2 }' "${NEW_MANIFEST_NORM}" > "${NEW_MANIFEST_RAW}"

cp "${NEW_MANIFEST_RAW}" "${PAYLOAD_DIR}/manifest.sha256"
cp "${CHANGED_LIST}" "${PAYLOAD_DIR}/changed-files.txt"
cp "${REMOVED_LIST}" "${PAYLOAD_DIR}/removed-files.txt"
cp "apply-gpu-delta.sh" "${PAYLOAD_DIR}/apply-gpu-delta.sh"
chmod +x "${PAYLOAD_DIR}/apply-gpu-delta.sh"

cat > "${PAYLOAD_DIR}/delta-info.txt" <<EOF
project=${PROJECT_NAME}
target=ubuntu2004-gpu-source
version=${VERSION}
created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
base_commit=${BASE_COMMIT:-}
changed_files=$(wc -l < "${CHANGED_LIST}" | tr -d ' ')
removed_files=$(wc -l < "${REMOVED_LIST}" | tr -d ' ')
requires_full_build=false
EOF

ARCHIVE_NAME="${PROJECT_NAME}-source-delta-${VERSION}.tar.gz"
ARCHIVE_PATH="${DELTA_ROOT}/${ARCHIVE_NAME}"
echo ">>> 压缩源码增量包: ${ARCHIVE_PATH}"
tar -czf "${ARCHIVE_PATH}" -C "${PAYLOAD_DIR}" .

echo "============================================"
echo "  GPU 源码增量包生成完成"
echo "============================================"
echo "  Base manifest: ${BASE_MANIFEST}"
echo "  Base commit:   ${BASE_COMMIT:-未指定}"
echo "  增量包:        ${ARCHIVE_PATH}"
echo "  增量包大小:    $(du -sh "${ARCHIVE_PATH}" | awk '{print $1}')"
echo "  变更文件数:    $(wc -l < "${CHANGED_LIST}" | tr -d ' ')"
echo "  删除文件数:    $(wc -l < "${REMOVED_LIST}" | tr -d ' ')"
echo "============================================"
