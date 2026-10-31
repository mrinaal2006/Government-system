#!/usr/bin/env bash
# Build the backend and web images with plain `docker build`.
#
# `docker compose build` works on ordinary networks. Use this script when building
# behind a TLS-inspecting proxy, where host networking and a CA bundle are needed
# (Compose's bake builder requires interactive entitlement approval for those).
#
#   BUILD_HTTPS_PROXY=http://proxy:3128 BUILD_CA_BUNDLE=/path/ca.pem BUILD_NETWORK=host \
#     ./scripts/build-images.sh
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${APP_VERSION:-0.1.0}"
CA="${BUILD_CA_BUNDLE:-infra/build/no-extra-ca.pem}"
args=(--secret "id=build_ca,src=${CA}")
[ -n "${BUILD_NETWORK:-}" ] && args+=(--network "${BUILD_NETWORK}")
[ -n "${BUILD_HTTPS_PROXY:-}" ] && args+=(--build-arg "HTTPS_PROXY=${BUILD_HTTPS_PROXY}")

docker build "${args[@]}" -t "dgimews-backend:${VERSION}" backend
docker build "${args[@]}" -t "dgimews-web:${VERSION}" -f infra/nginx/Dockerfile .
echo "Built dgimews-backend:${VERSION} and dgimews-web:${VERSION}"
