#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-1.0.0}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="${SCRIPT_DIR}/dist-output"
IMAGE_TAG="icu-builder:cpu-universal"
PACKAGE_NAME="icu-alert-system-linux-universal-${VERSION}.tar.gz"

mkdir -p "${OUT}"

echo "[build] cpu-universal -> ${PACKAGE_NAME}"
docker build \
    --build-arg APP_VERSION="${VERSION}" \
    -f "${SCRIPT_DIR}/Dockerfile.universal-build" \
    -t "${IMAGE_TAG}" \
    "${SCRIPT_DIR}"

container_id="$(docker create "${IMAGE_TAG}")"
docker cp "${container_id}:/output/${PACKAGE_NAME}" "${OUT}/${PACKAGE_NAME}"
docker rm "${container_id}" >/dev/null

echo ""
echo "Artifacts:"
ls -lh "${OUT}/${PACKAGE_NAME}"
