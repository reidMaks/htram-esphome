#!/usr/bin/env bash
# =============================================================================
# Antigravity Remote Control Daemon Management Script
# =============================================================================

set -euo pipefail

LOG_DIR="${HOME}/.gemini/antigravity-cli"
LOG_FILE="${LOG_DIR}/remote-control.log"
PID_FILE="/tmp/agy-remote-control.pid"

find_agy() {
    if command -v agy >/dev/null 2>&1; then
        command -v agy
        return 0
    fi
    for path in "/home/ubuntu/.gemini/bin/agy" "${HOME}/.gemini/bin/agy" "/host-bin/agy"; do
        if [ -x "${path}" ]; then
            echo "${path}"
            return 0
        fi
    done
    return 1
}

get_daemon_pid() {
    if [ -f "${PID_FILE}" ]; then
        local pid
        pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
        if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
            if ps -p "${pid}" -o args= 2>/dev/null | grep -q "agy remote-control serve"; then
                echo "${pid}"
                return 0
            fi
        fi
    fi
    # Fallback to pgrep
    pgrep -f "agy remote-control serve" 2>/dev/null | head -n 1 || true
}

start_daemon() {
    local pid
    pid="$(get_daemon_pid)"
    if [ -n "${pid}" ]; then
        echo "Antigravity Remote Control daemon is already running (PID: ${pid})."
        return 0
    fi

    local agy_bin
    if ! agy_bin="$(find_agy)"; then
        echo "Error: 'agy' binary not found. Ensure ~/.gemini/bin or ~/.local/bin is mounted." >&2
        return 1
    fi

    mkdir -p "${LOG_DIR}"
    echo "Starting Antigravity Remote Control daemon (${agy_bin})..."
    nohup "${agy_bin}" remote-control serve > "${LOG_FILE}" 2>&1 &
    local new_pid=$!
    echo "${new_pid}" > "${PID_FILE}"

    sleep 1.5
    if kill -0 "${new_pid}" 2>/dev/null; then
        echo "Antigravity Remote Control daemon started successfully (PID: ${new_pid})."
        local hostname=""
        if [ -f "${HOME}/.gemini/config/config.json" ]; then
            hostname="$(grep -o '"cliRemoteControlHostname": "[^"]*"' "${HOME}/.gemini/config/config.json" | cut -d'"' -f4 || true)"
        fi
        if [ -n "${hostname}" ]; then
            echo "Instance: ${hostname} (accessible at https://antigravity.google.com)"
        fi
        echo "Logs: ${LOG_FILE}"
    else
        echo "Error: Daemon failed to start. Last log lines:" >&2
        tail -n 20 "${LOG_FILE}" 2>/dev/null || true
        rm -f "${PID_FILE}"
        return 1
    fi
}

stop_daemon() {
    local pid
    pid="$(get_daemon_pid)"
    if [ -z "${pid}" ]; then
        echo "Antigravity Remote Control daemon is not running."
        rm -f "${PID_FILE}"
        return 0
    fi

    echo "Stopping Antigravity Remote Control daemon (PID: ${pid})..."
    kill "${pid}" 2>/dev/null || true

    for _ in {1..10}; do
        if ! kill -0 "${pid}" 2>/dev/null; then
            break
        fi
        sleep 0.5
    done

    if kill -0 "${pid}" 2>/dev/null; then
        echo "Forcing termination (SIGKILL)..."
        kill -9 "${pid}" 2>/dev/null || true
    fi

    rm -f "${PID_FILE}"
    echo "Antigravity Remote Control daemon stopped."
}

status_daemon() {
    local pid
    pid="$(get_daemon_pid)"
    if [ -n "${pid}" ]; then
        echo "Status: RUNNING (PID: ${pid})"
        ps -p "${pid}" -o pid,user,%cpu,%mem,etime,command 2>/dev/null || true

        local hostname=""
        if [ -f "${HOME}/.gemini/config/config.json" ]; then
            hostname="$(grep -o '"cliRemoteControlHostname": "[^"]*"' "${HOME}/.gemini/config/config.json" | cut -d'"' -f4 || true)"
        fi
        if [ -n "${hostname}" ]; then
            echo "Instance: ${hostname} (accessible at https://antigravity.google.com)"
        fi

        local latest_cli_log
        latest_cli_log="$(ls -t "${LOG_DIR}/log"/cli-*.log 2>/dev/null | head -n 1 || true)"
        if [ -n "${latest_cli_log}" ] && [ -f "${latest_cli_log}" ]; then
            local conn_status
            conn_status="$(grep -E "Connection status:" "${latest_cli_log}" | tail -n 1 || true)"
            if [ -n "${conn_status}" ]; then
                echo "Channel:  ${conn_status}"
            fi
        fi

        echo ""
        if [ -f "${LOG_FILE}" ]; then
            echo "--- Latest daemon output (${LOG_FILE}) ---"
            tail -n 5 "${LOG_FILE}"
        fi
    else
        echo "Status: STOPPED"
        if [ -f "${LOG_FILE}" ]; then
            echo ""
            echo "--- Last known daemon output (${LOG_FILE}) ---"
            tail -n 5 "${LOG_FILE}"
        fi
    fi
}

show_logs() {
    if [ ! -f "${LOG_FILE}" ]; then
        echo "Log file not found: ${LOG_FILE}"
        return 1
    fi
    if [ "${1:-}" = "-f" ]; then
        tail -f "${LOG_FILE}"
    else
        tail -n "${1:-50}" "${LOG_FILE}"
    fi
}

usage() {
    echo "Usage: $0 {start|stop|restart|status|logs [-f|<lines>]}"
    exit 1
}

case "${1:-}" in
    start)
        start_daemon
        ;;
    stop)
        stop_daemon
        ;;
    restart)
        stop_daemon
        start_daemon
        ;;
    status)
        status_daemon
        ;;
    logs|log)
        shift
        show_logs "$@"
        ;;
    *)
        usage
        ;;
esac
