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

find_running_container() {
    local cid
    cid="$(docker ps -q -f name="^/${CONTAINER_NAME}$" 2>/dev/null || true)"
    if [ -n "${cid}" ]; then
        echo "${cid}"
        return 0
    fi
    cid="$(docker ps -q --filter "label=devcontainer.local_folder=${WORKSPACE_ROOT}" 2>/dev/null | head -n 1 || true)"
    if [ -n "${cid}" ]; then
        echo "${cid}"
        return 0
    fi
    return 1
}

run_container() {
    local cid
    if cid="$(find_running_container)"; then
        echo "==> Attaching interactive shell to running container (${cid})..."
        docker exec -it -w /workspaces/htram-esphome "${cid}" bash
        return 0
    fi

    ensure_volumes
    if [ "$(docker ps -aq -f status=exited -f name=^/${CONTAINER_NAME}$)" ]; then
        echo "==> Starting existing stopped container: ${CONTAINER_NAME}..."
        docker start "${CONTAINER_NAME}" >/dev/null
    else
        echo "==> Running new container: ${CONTAINER_NAME}..."
        docker run -d \
            --name "${CONTAINER_NAME}" \
            --network=host \
            --privileged \
            --cpus=7.0 \
            -v /dev:/dev \
            -v /run/udev:/run/udev:ro \
            -v "${WORKSPACE_ROOT}:/workspaces/htram-esphome" \
            -v htram-platformio:/home/ubuntu/.platformio \
            -v htram-cache:/home/ubuntu/.cache \
            -v "${HOME}/.gemini:/home/ubuntu/.gemini" \
            -v "${HOME}/.local/bin:/host-bin:ro" \
            -w /workspaces/htram-esphome \
            "${IMAGE_NAME}" \
            sleep infinity
    fi
    docker exec "${CONTAINER_NAME}" bash /workspaces/htram-esphome/tools/remote-control.sh start >/dev/null 2>&1 || true

    echo "==> Attaching interactive shell to ${CONTAINER_NAME}..."
    docker exec -it -w /workspaces/htram-esphome "${CONTAINER_NAME}" bash
}

exec_command() {
    local cid
    if ! cid="$(find_running_container)"; then
        echo "Error: No running container found. Run '$0 run' first." >&2
        return 1
    fi
    # Use -t only if running attached to a terminal
    local tty_flag=""
    if [ -t 0 ]; then
        tty_flag="-it"
    fi
    docker exec ${tty_flag} -w /workspaces/htram-esphome "${cid}" "$@"
}

stop_container() {
    echo "==> Stopping container: ${CONTAINER_NAME}..."
    docker stop "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    docker rm "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    echo "Done."
}

usage() {
    echo "Usage: $0 {build|run|exec <cmd>|stop|remote-control <subcommand>}"
    echo ""
    echo "Commands:"
    echo "  build                   Build the htram-dev Docker image"
    echo "  run                     Start container (if not running) and open an interactive bash shell"
    echo "  exec <cmd>              Execute a command inside the running container"
    echo "  remote-control <cmd>    Manage Antigravity Remote Control (start|stop|restart|status|logs)"
    echo "  stop                    Stop and remove the container"
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
    remote-control)
        shift
        exec_command /workspaces/htram-esphome/tools/remote-control.sh "$@"
        ;;
    stop)
        stop_container
        ;;
    *)
        usage
        ;;
esac
