#!/bin/bash
# ============================================================
#  ICU Alert System 一键打包
#  用法: ./build.sh [版本号]
#  支持: OEL9 / CentOS / Ubuntu / macOS / Windows(Git Bash)
#  前提: 装了 Docker
# ============================================================
set -e
VERSION="${1:-1.0.0}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="${SCRIPT_DIR}/dist-output"
mkdir -p "$OUT"

echo ""
echo "======================================"
echo "  ICU Alert System 打包 v${VERSION}"
echo "  编译目标: OEL 8.2+ (glibc 2.28)"
echo "======================================"
echo ""

# 构建编译镜像（有 Docker 缓存，第二次起很快）
echo "[1/2] 构建编译镜像..."
docker build -f Dockerfile.build -t icu-builder:latest .

# 把产物拷出来
echo "[2/2] 提取产物..."
CONTAINER_ID=$(docker create icu-builder:latest)
docker cp "${CONTAINER_ID}:/output/icu-alert-system.tar.gz" \
    "${OUT}/icu-alert-system-${VERSION}.el8.x86_64.tar.gz"
docker rm "${CONTAINER_ID}" > /dev/null

echo ""
echo "======================================"
echo "  打包完成!"
echo "======================================"
echo ""
ls -lh "${OUT}/icu-alert-system-${VERSION}.el8.x86_64.tar.gz"
echo ""
echo "部署到 OEL 8.2:"
echo "  scp ${OUT}/icu-alert-system-${VERSION}.el8.x86_64.tar.gz root@目标机:/opt/"
echo "  ssh root@目标机 'cd /opt && tar xzf icu-alert-system-${VERSION}.el8.x86_64.tar.gz'"
echo "  ssh root@目标机 '/opt/icu-alert-system/install.sh'"