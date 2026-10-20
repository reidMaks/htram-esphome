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

is_daemon_stale() {
    local pid="$1"
    local agy_bin="$2"
    local proc_exe
    proc_exe="$(readlink "/proc/${pid}/exe" 2>/dev/null || true)"
    if [ -z "${proc_exe}" ]; then
        return 1
    fi
    case "${proc_exe}" in
        *"(deleted)"*|*".old."*)
            return 0
            ;;
    esac
    local real_agy
    real_agy="$(readlink -f "${agy_bin}" 2>/dev/null || echo "${agy_bin}")"
    if [ "${proc_exe}" != "${real_agy}" ]; then
        return 0
    fi
    return 1
}

ensure_inotify_limits() {
    local current_instances
    current_instances="$(cat /proc/sys/fs/inotify/max_user_instances 2>/dev/null || echo 128)"
    if [ "${current_instances}" -lt 1024 ] 2>/dev/null; then
        sudo -n sysctl -w fs.inotify.max_user_instances=1024 >/dev/null 2>&1 || true
    fi
}

find_daemon_log() {
    local pid="$1"
    grep -l "Starting language server process with pid ${pid}\$" "${LOG_DIR}/log"/cli-*.log 2>/dev/null | tail -n 1 || true
}

start_daemon() {
    ensure_inotify_limits

    local agy_bin
    if ! agy_bin="$(find_agy)"; then
        echo "Error: 'agy' binary not found. Ensure ~/.gemini/bin or ~/.local/bin is mounted." >&2
        return 1
    fi

    local pid
    pid="$(get_daemon_pid)"
    if [ -n "${pid}" ]; then
        if is_daemon_stale "${pid}" "${agy_bin}"; then
            echo "Antigravity Remote Control daemon (PID: ${pid}) is running an outdated binary after auto-update. Restarting..."
            stop_daemon
        else
            echo "Antigravity Remote Control daemon is already running (PID: ${pid})."
            return 0
        fi
    fi

    mkdir -p "${LOG_DIR}"
    echo "Starting Antigravity Remote Control daemon (${agy_bin})..."
    setsid "${agy_bin}" remote-control serve > "${LOG_FILE}" 2>&1 < /dev/null &
    local new_pid=$!
    echo "${new_pid}" > "${PID_FILE}"

    sleep 2
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

        local agy_bin
        agy_bin="$(find_agy 2>/dev/null || true)"
        local proc_exe
        proc_exe="$(readlink "/proc/${pid}/exe" 2>/dev/null || true)"
        if [ -n "${agy_bin}" ] && is_daemon_stale "${pid}" "${agy_bin}"; then
            echo "Binary:   ${proc_exe} (STALE - run '$0 restart' to update to ${agy_bin})"
        elif [ -n "${proc_exe}" ]; then
            echo "Binary:   ${proc_exe} (up-to-date)"
        fi

        local hostname=""
        if [ -f "${HOME}/.gemini/config/config.json" ]; then
            hostname="$(grep -o '"cliRemoteControlHostname": "[^"]*"' "${HOME}/.gemini/config/config.json" | cut -d'"' -f4 || true)"
        fi
        if [ -n "${hostname}" ]; then
            echo "Instance: ${hostname} (accessible at https://antigravity.google.com)"
            echo "Project:  CLI Project (/workspaces/htram-esphome)"
        fi

        local daemon_log
        daemon_log="$(find_daemon_log "${pid}")"
        if [ -n "${daemon_log}" ] && [ -f "${daemon_log}" ]; then
            local ls_ver
            ls_ver="$(grep -E "Language server version:" "${daemon_log}" | tail -n 1 || true)"
            if [ -n "${ls_ver}" ]; then
                echo "Version:  ${ls_ver}"
            fi
            local conn_status
            conn_status="$(grep -E "Connection status:" "${daemon_log}" | tail -n 1 || true)"
            if [ -n "${conn_status}" ]; then
                echo "Channel:  ${conn_status}"
            fi
            local sync_status
            sync_status="$(grep -E "\[Summaries\] reconcile checked" "${daemon_log}" | tail -n 1 || true)"
            if [ -n "${sync_status}" ]; then
                echo "Synced:   ${sync_status}"
            fi
        fi

        echo ""
        if [ -f "${LOG_FILE}" ] && [ -s "${LOG_FILE}" ]; then
            echo "--- Latest daemon stdout/stderr (${LOG_FILE}) ---"
            tail -n 5 "${LOG_FILE}"
        fi
    else
        echo "Status: STOPPED"
        if [ -f "${LOG_FILE}" ] && [ -s "${LOG_FILE}" ]; then
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
