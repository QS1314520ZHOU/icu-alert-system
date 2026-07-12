#!/bin/bash
set -euo pipefail

VERSION="${1:-1.0.0}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="${SCRIPT_DIR}/dist-output"
IMAGE_TAG="icu-builder:oel10-cpu"
PACKAGE_NAME="icu-alert-system-cpu"
ARTIFACT="${PACKAGE_NAME}-${VERSION}.el10.x86_64.tar.gz"

mkdir -p "$OUT"

echo "[build] oel10 cpu -> ${ARTIFACT}"
docker build \
    --pull \
    --build-arg APP_VERSION="${VERSION}" \
    -f "${SCRIPT_DIR}/Dockerfile.build.oel10" \
    -t "${IMAGE_TAG}" \
    "${SCRIPT_DIR}"

# 从构建产物镜像里拷出 tar 包
container_id="$(docker create "${IMAGE_TAG}")"
docker cp "${container_id}:/output/${ARTIFACT}" "${OUT}/${ARTIFACT}"
docker rm "${container_id}" >/dev/null

echo ""
echo "Artifact:"
ls -lh "${OUT}/${ARTIFACT}"
echo ""
echo "部署到 OEL10 主机:"
echo "  scp ${OUT}/${ARTIFACT} user@host:/opt/"
echo "  cd /opt && tar xzf ${ARTIFACT}"
echo "  cd ${PACKAGE_NAME} && vi .env && ./install.sh && systemctl start icu-alert"
