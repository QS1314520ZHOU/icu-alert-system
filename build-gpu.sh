#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="icu-alert-system"
IMAGE_NAME="${PROJECT_NAME}-gpu-builder"
OUTPUT_DIR="dist/${PROJECT_NAME}-ubuntu2004-gpu"

echo "============================================"
echo "  ICU Alert System - GPU 打包构建 (优化版)"
echo "============================================"

# ---- 预检 ----
if ! command -v docker &>/dev/null; then
    echo "错误: 未安装 Docker"; exit 1
fi

if [ ! -d "backend" ] || [ ! -d "frontend" ]; then
    echo "未找到 backend/frontend 目录，正在克隆..."
    git clone https://github.com/QS1314520ZHOU/icu-alert-system.git _tmp_src
    cp -r _tmp_src/backend ./backend
    cp -r _tmp_src/frontend ./frontend
    rm -rf _tmp_src
fi

if [ ! -f "entry.py" ]; then
    echo "错误: 缺少 entry.py"; exit 1
fi

# ---- .dockerignore ----
if [ ! -f ".dockerignore" ]; then
    cat > .dockerignore << 'EOF'
.git
node_modules
__pycache__
*.pyc
dist
build
.venv
venv
*.egg-info
.env
EOF
    echo ">>> 已生成 .dockerignore"
fi

# ---- 构建 ----
echo ""
echo ">>> 开始 Docker 构建..."
echo ">>> 首次约 10-15 分钟, 后续改代码重建约 2-5 分钟"
echo ""

export DOCKER_BUILDKIT=1

if docker buildx version &>/dev/null 2>&1; then
    echo ">>> 使用 docker buildx (并行构建 + cache mount)"
    docker buildx build \
        --load \
        -t "${IMAGE_NAME}" \
        -f Dockerfile.gpu-build \
        .
else
    echo ">>> 使用 docker build (BuildKit)"
    docker build \
        -t "${IMAGE_NAME}" \
        -f Dockerfile.gpu-build \
        .
fi

# ---- 提取产物并压缩 ----
echo ""
echo ">>> 提取构建产物..."
rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"

CONTAINER_ID=$(docker create "${IMAGE_NAME}")
docker cp "${CONTAINER_ID}:/build/output/." "${OUTPUT_DIR}/"
docker rm "${CONTAINER_ID}"

echo ">>> 生成完整包 manifest..."
(cd "${OUTPUT_DIR}" && \
    find . -type f \
        ! -name 'manifest.sha256' \
        ! -path './.env' \
        ! -name '*.pid' \
        ! -name '*.log' \
        ! -path './backups/*' \
        ! -path './.delta-backups/*' \
        -print | sort | while IFS= read -r file; do
            sha256sum "$file" | sed 's#  \./#  #'
        done > manifest.sha256)

# 压缩
ARCHIVE_NAME="${PROJECT_NAME}-ubuntu2004-gpu.tar.gz"
ARCHIVE_PATH="dist/${ARCHIVE_NAME}"
echo ">>> 压缩打包: ${ARCHIVE_PATH}"
tar -czf "${ARCHIVE_PATH}" -C "dist" "$(basename "${OUTPUT_DIR}")"
ARCHIVE_SIZE=$(du -sh "${ARCHIVE_PATH}" | cut -f1)
echo ">>> 压缩完成: ${ARCHIVE_SIZE}"

# ---- 验证 ----
echo ""
if [ -f "${OUTPUT_DIR}/${PROJECT_NAME}" ]; then
    chmod +x "${OUTPUT_DIR}/${PROJECT_NAME}"
    chmod +x "${OUTPUT_DIR}/run.sh" 2>/dev/null || true
    echo "============================================"
    echo "  构建成功! (GPU 版, 含 CUDA 12.1 运行库)"
    echo "============================================"
    echo "  产物目录:  ${OUTPUT_DIR}/"
    echo "  压缩包:    ${ARCHIVE_PATH} (${ARCHIVE_SIZE})"
    echo "  二进制:    $(du -sh "${OUTPUT_DIR}/${PROJECT_NAME}" | cut -f1)"
    echo "  未压缩总:  $(du -sh "${OUTPUT_DIR}" | cut -f1)"
    echo ""
    echo "  部署步骤:"
    echo "  1. scp ${ARCHIVE_PATH} user@gpu-server:/opt/"
    echo "  2. cd /opt && tar xzf ${ARCHIVE_NAME}"
    echo "  3. cd ${PROJECT_NAME}-ubuntu2004-gpu"
    echo "  4. cp .env.template .env && vim .env"
    echo "  5. ./run.sh start"
    echo "============================================"
else
    echo "构建失败！产物不存在"
    echo "查看日志: docker run --rm ${IMAGE_NAME} tail -100 /build/pyinstaller.log"
    exit 1
fi
