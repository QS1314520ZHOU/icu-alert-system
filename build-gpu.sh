#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="icu-alert-system"
IMAGE_NAME="${PROJECT_NAME}-gpu-builder"
OUTPUT_DIR="dist/${PROJECT_NAME}-ubuntu2004-gpu"

echo "============================================"
echo "  ICU Alert System - GPU 打包构建"
echo "============================================"

# 检查 Docker
if ! command -v docker &>/dev/null; then
    echo "错误: 未安装 Docker"
    echo "安装: curl -fsSL https://get.docker.com | sh"
    exit 1
fi

# 检查源码
if [ ! -d "backend" ] || [ ! -d "frontend" ]; then
    echo "未找到 backend/frontend 目录，正在克隆..."
    git clone https://github.com/QS1314520ZHOU/icu-alert-system.git _tmp_src
    cp -r _tmp_src/backend ./backend
    cp -r _tmp_src/frontend ./frontend
    rm -rf _tmp_src
fi

# 检查 entry.py
if [ ! -f "entry.py" ]; then
    echo "错误: 缺少 entry.py，请先创建"
    exit 1
fi

# 构建 Docker 镜像
echo ""
echo ">>> 开始 Docker 构建 (首次约 15-30 分钟)..."
docker build \
    --network=host \
    -t "${IMAGE_NAME}" \
    -f Dockerfile.gpu-build \
    .

# 提取产物
echo ""
echo ">>> 提取构建产物..."
rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"

CONTAINER_ID=$(docker create "${IMAGE_NAME}")
docker cp "${CONTAINER_ID}:/build/output/." "${OUTPUT_DIR}/"
docker rm "${CONTAINER_ID}"

# 验证
echo ""
if [ -f "${OUTPUT_DIR}/${PROJECT_NAME}" ]; then
    chmod +x "${OUTPUT_DIR}/${PROJECT_NAME}"
    chmod +x "${OUTPUT_DIR}/run.sh"
    echo "============================================"
    echo "  构建成功！"
    echo "============================================"
    echo "  产物目录: ${OUTPUT_DIR}/"
    echo "  二进制大小: $(du -sh "${OUTPUT_DIR}/${PROJECT_NAME}" | cut -f1)"
    echo "  总大小: $(du -sh "${OUTPUT_DIR}" | cut -f1)"
    echo ""
    echo "  部署步骤:"
    echo "  1. scp -r ${OUTPUT_DIR}/ user@server:/opt/${PROJECT_NAME}/"
    echo "  2. cd /opt/${PROJECT_NAME}"
    echo "  3. cp .env.template .env && vim .env"
    echo "  4. chmod +x ${PROJECT_NAME} run.sh"
    echo "  5. ./run.sh start-bg"
    echo "============================================"
else
    echo "构建失败！产物不存在"
    echo "查看日志: docker run --rm ${IMAGE_NAME} cat /build/pyinstaller.log | tail -50"
    exit 1
fi
