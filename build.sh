#!/bin/bash
set -euo pipefail

VERSION="${1:-1.0.0}"
VARIANT="${2:-both}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="${SCRIPT_DIR}/dist-output"

mkdir -p "$OUT"

build_variant() {
    local variant="$1"
    local image_tag="icu-builder:${variant}"
    local package_name="icu-alert-system-${variant}-${VERSION}.el8.x86_64.tar.gz"

    echo "[build] ${variant} -> ${package_name}"
    docker build \
        --build-arg BUILD_VARIANT="${variant}" \
        --build-arg APP_VERSION="${VERSION}" \
        -f "${SCRIPT_DIR}/Dockerfile.build" \
        -t "${image_tag}" \
        "${SCRIPT_DIR}"

    container_id="$(docker create "${image_tag}")"
    docker cp "${container_id}:/output/${package_name}" "${OUT}/${package_name}"
    docker rm "${container_id}" >/dev/null
}

case "${VARIANT}" in
    cpu|gpu)
        build_variant "${VARIANT}"
        ;;
    both)
        build_variant cpu
        build_variant gpu
        ;;
    *)
        echo "Usage: ./build.sh [version] [cpu|gpu|both]" >&2
        exit 1
        ;;
esac

echo ""
echo "Artifacts:"
ls -lh "${OUT}"/*.tar.gz
