#!/usr/bin/env bash
# =============================================================================
# Helper script to build, run, and interact with the HTRAM Dev Container
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE_NAME="htram-dev:latest"
CONTAINER_NAME="htram-dev"

build_image() {
    echo "==> Building Docker image: ${IMAGE_NAME}..."
    docker build \
        -f "${WORKSPACE_ROOT}/.devcontainer/Dockerfile" \
        -t "${IMAGE_NAME}" \
        "${WORKSPACE_ROOT}"
}

ensure_volumes() {
    docker volume create htram-platformio >/dev/null 2>&1 || true
    docker volume create htram-cache >/dev/null 2>&1 || true
}

run_container() {
    ensure_volumes
    if [ ! "$(docker ps -q -f name=^/${CONTAINER_NAME}$)" ]; then
        if [ "$(docker ps -aq -f status=exited -f name=^/${CONTAINER_NAME}$)" ]; then
            echo "==> Starting existing stopped container: ${CONTAINER_NAME}..."
            docker start "${CONTAINER_NAME}" >/dev/null
        else
            echo "==> Running new container: ${CONTAINER_NAME}..."
            docker run -d \
                --name "${CONTAINER_NAME}" \
                --network=host \
                --privileged \
                -v /dev:/dev \
                -v /run/udev:/run/udev:ro \
                -v "${WORKSPACE_ROOT}:/workspace" \
                -v htram-platformio:/home/ubuntu/.platformio \
                -v htram-cache:/home/ubuntu/.cache \
                -v "${HOME}/.gemini:/home/ubuntu/.gemini:ro" \
                -v "${HOME}/.local/bin:/host-bin:ro" \
                -w /workspace \
                "${IMAGE_NAME}" \
                sleep infinity
        fi
    fi

    echo "==> Attaching interactive shell to ${CONTAINER_NAME}..."
    docker exec -it "${CONTAINER_NAME}" bash
}

exec_command() {
    ensure_volumes
    if [ ! "$(docker ps -q -f name=^/${CONTAINER_NAME}$)" ]; then
        run_container
    fi
    docker exec -it "${CONTAINER_NAME}" "$@"
}

stop_container() {
    echo "==> Stopping container: ${CONTAINER_NAME}..."
    docker stop "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    docker rm "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    echo "Done."
}

usage() {
    echo "Usage: $0 {build|run|exec <cmd>|stop}"
    echo ""
    echo "Commands:"
    echo "  build         Build the htram-dev Docker image"
    echo "  run           Start container (if not running) and open an interactive bash shell"
    echo "  exec <cmd>    Execute a command inside the running container"
    echo "  stop          Stop and remove the container"
    exit 1
}

case "${1:-}" in
    build)
        build_image
        ;;
    run)
        run_container
        ;;
    exec)
        shift
        exec_command "$@"
        ;;
    stop)
        stop_container
        ;;
    *)
        usage
        ;;
esac
