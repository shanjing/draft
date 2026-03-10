#!/bin/bash
# draft.sh — Local daemon manager for Draft UI and MCP server.
#
# This script manages LOCAL background processes only.
# For Docker: see docs/container_orchestration_guide.md
# For Kubernetes: helm install draft ./kubernetes/draft --namespace draft
#
# Usage:
#   ./draft.sh status
#   ./draft.sh ui  start|stop|restart  [-p PORT]
#   ./draft.sh mcp start|stop|restart|logs  [--log-json]
#   ./draft.sh mcp start --stdio           (foreground, for Claude Desktop)

set -eo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

PYTHON="${REPO_ROOT}/.venv/bin/python"
[ ! -x "$PYTHON" ] && PYTHON="python3"

: "${DRAFT_HOME:="$HOME/.draft"}"
export DRAFT_HOME
mkdir -p "$DRAFT_HOME"

# ── Service defaults ──────────────────────────────────────────────────────────

UI_PORT=8058
UI_LOG="${DRAFT_HOME}/.draft-ui.log"
UI_PID="${DRAFT_HOME}/.draft-ui.pid"

MCP_PORT=8059
MCP_LOG="${DRAFT_HOME}/draft-mcp.log"
MCP_PID="${DRAFT_HOME}/draft-mcp.pid"

# ── Low-level helpers ─────────────────────────────────────────────────────────

pid_alive() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }

read_pid() { [ -f "$1" ] && cat "$1" || echo ""; }

port_in_use() {
  local port="$1"
  "$PYTHON" -c "
import socket, sys
s = socket.socket()
s.settimeout(1)
try: s.connect(('127.0.0.1', $port)); s.close(); sys.exit(0)
except: sys.exit(1)
" 2>/dev/null
}

# Guaranteed kill: SIGTERM → wait up to 5s → SIGKILL → port sweep.
# Leaves no stale process behind.
sure_kill() {
  local pid="${1:-}" port="${2:-}"

  if pid_alive "$pid"; then
    kill -TERM "$pid" 2>/dev/null || true
    local i=0
    while pid_alive "$pid" && [ "$i" -lt 5 ]; do sleep 1; i=$((i+1)); done
    pid_alive "$pid" && kill -KILL "$pid" 2>/dev/null || true
    sleep 0.3
  fi

  if [ -n "$port" ]; then
    local stale
    stale="$(lsof -ti ":$port" 2>/dev/null || true)"
    if [ -n "$stale" ]; then
      echo "$stale" | xargs kill -KILL 2>/dev/null || true
      sleep 0.3
    fi
  fi
}

health_check() {
  curl -sf "http://127.0.0.1:${1}/health" 2>/dev/null || true
}

# ── UI ────────────────────────────────────────────────────────────────────────

ui_stop() {
  local pid
  pid=$(read_pid "$UI_PID")
  if pid_alive "$pid" || port_in_use "$UI_PORT"; then
    echo "[UI] Stopping (port $UI_PORT)..."
    sure_kill "$pid" "$UI_PORT"
    echo "[UI] Stopped."
  else
    echo "[UI] Not running."
  fi
  rm -f "$UI_PID"
}

ui_start() {
  local pid
  pid=$(read_pid "$UI_PID")
  if pid_alive "$pid" || port_in_use "$UI_PORT"; then
    echo "[UI] Already running on port $UI_PORT. Use 'restart' to restart."
    return
  fi
  echo "[UI] Starting Draft UI (local daemon, port $UI_PORT)..."
  nohup "$PYTHON" "$REPO_ROOT/scripts/serve.py" -p "$UI_PORT" \
    >> "$UI_LOG" 2>&1 &
  local new_pid=$!
  echo "$new_pid" > "$UI_PID"
  sleep 2
  if pid_alive "$new_pid"; then
    echo "[UI] Running (PID $new_pid)."
    echo "[UI] Log:  $UI_LOG"
    echo "[UI] Open: http://localhost:$UI_PORT"
    echo "[UI] Stop: ./draft.sh ui stop"
    case "$(uname -s)" in
      Darwin) open "http://localhost:$UI_PORT" ;;
      *)      xdg-open "http://localhost:$UI_PORT" 2>/dev/null || true ;;
    esac
  else
    echo "[UI] Failed to start. Check log:"
    tail -15 "$UI_LOG" 2>/dev/null || true
    rm -f "$UI_PID"; exit 1
  fi
}

ui_restart() {
  ui_stop
  sleep 1
  ui_start
}

# ── MCP ───────────────────────────────────────────────────────────────────────

mcp_stop() {
  local pid
  pid=$(read_pid "$MCP_PID")
  if pid_alive "$pid" || port_in_use "$MCP_PORT"; then
    echo "[MCP] Stopping (port $MCP_PORT)..."
    sure_kill "$pid" "$MCP_PORT"
    echo "[MCP] Stopped."
  else
    echo "[MCP] Not running."
  fi
  rm -f "$MCP_PID"
}

mcp_start_http() {
  local log_json="${1:-0}"
  local pid
  pid=$(read_pid "$MCP_PID")
  if pid_alive "$pid" || port_in_use "$MCP_PORT"; then
    echo "[MCP] Already running on port $MCP_PORT. Use 'restart' to restart."
    return
  fi
  echo "[MCP] Starting Draft MCP server (local daemon, HTTP, port $MCP_PORT)..."
  if [ "$log_json" -eq 1 ]; then
    nohup env MCP_LOG_JSON=1 \
      "$PYTHON" "$REPO_ROOT/scripts/serve_mcp.py" >> "$MCP_LOG" 2>&1 &
  else
    nohup "$PYTHON" "$REPO_ROOT/scripts/serve_mcp.py" >> "$MCP_LOG" 2>&1 &
  fi
  local new_pid=$!
  echo "$new_pid" > "$MCP_PID"
  sleep 2
  if pid_alive "$new_pid"; then
    local health
    health=$(health_check "$MCP_PORT")
    echo "[MCP] Running (PID $new_pid, port $MCP_PORT)."
    [ -n "$health" ] && echo "[MCP] Health: $health"
    echo "[MCP] Log:  $MCP_LOG"
    echo "[MCP] Stop: ./draft.sh mcp stop"
  else
    echo "[MCP] Failed to start. Check log:"
    tail -15 "$MCP_LOG" 2>/dev/null || true
    rm -f "$MCP_PID"; exit 1
  fi
}

mcp_start_stdio() {
  echo "[MCP] Starting Draft MCP server (local, stdio, foreground)."
  echo "[MCP] Log → $MCP_LOG"
  exec "$PYTHON" "$REPO_ROOT/scripts/serve_mcp.py" --stdio
}

mcp_restart() {
  mcp_stop
  sleep 1
  mcp_start_http "${1:-0}"
}

mcp_logs() {
  if [ ! -f "$MCP_LOG" ]; then
    echo "[MCP] No log yet: $MCP_LOG"; exit 1
  fi
  echo "Tailing $MCP_LOG  (Ctrl-C to stop)"
  tail -f "$MCP_LOG"
}

# ── Status ────────────────────────────────────────────────────────────────────

do_status() {
  local line="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  echo "$line"
  echo "  Draft — LOCAL daemon status"
  echo "  (Docker/K8s: docs/container_orchestration_guide.md)"
  echo "$line"
  echo ""

  # UI
  local ui_pid ui_state
  ui_pid=$(read_pid "$UI_PID")
  if pid_alive "$ui_pid"; then
    ui_state="RUNNING  PID $ui_pid"
  elif port_in_use "$UI_PORT"; then
    ui_state="RUNNING  (no PID file — started outside this script)"
  else
    ui_state="STOPPED"
  fi
  printf "  %-10s  port %s  →  %s\n" "Draft UI" "$UI_PORT" "$ui_state"

  # MCP
  local mcp_pid mcp_state health
  mcp_pid=$(read_pid "$MCP_PID")
  if pid_alive "$mcp_pid"; then
    health=$(health_check "$MCP_PORT")
    mcp_state="RUNNING  PID $mcp_pid"
    [ -n "$health" ] && mcp_state="$mcp_state  |  $health"
  elif port_in_use "$MCP_PORT"; then
    health=$(health_check "$MCP_PORT")
    mcp_state="RUNNING  (no PID file)"
    [ -n "$health" ] && mcp_state="$mcp_state  |  $health"
  else
    mcp_state="STOPPED"
  fi
  printf "  %-10s  port %s  →  %s\n" "Draft MCP" "$MCP_PORT" "$mcp_state"

  echo ""
  echo "  DRAFT_HOME : $DRAFT_HOME"
  echo "  UI  log    : $UI_LOG"
  echo "  MCP log    : $MCP_LOG"
  echo "$line"
}

# ── Usage ─────────────────────────────────────────────────────────────────────

usage() {
  echo "Draft local daemon manager  (NOT Docker or Kubernetes)"
  echo ""
  echo "Usage: $0 status"
  echo "       $0 ui  start|stop|restart  [-p PORT]"
  echo "       $0 mcp start|stop|restart|logs  [--log-json]"
  echo "       $0 mcp start --stdio"
  echo ""
  echo "Commands:"
  echo "  status                   Show running state of both UI and MCP"
  echo ""
  echo "  ui start   [-p PORT]     Start UI daemon (default port $UI_PORT)"
  echo "  ui stop    [-p PORT]     Stop UI daemon (force-kills stale process)"
  echo "  ui restart [-p PORT]     Stop then start UI"
  echo ""
  echo "  mcp start  [--log-json]  Start MCP HTTP daemon (port $MCP_PORT)"
  echo "  mcp start  --stdio       Start MCP stdio transport (foreground)"
  echo "  mcp stop                 Stop MCP daemon (force-kills stale process)"
  echo "  mcp restart              Stop then start MCP"
  echo "  mcp logs                 Tail MCP server log"
  echo ""
  echo "Other run modes:"
  echo "  Docker:     see docs/container_orchestration_guide.md"
  echo "  Kubernetes: helm install draft ./kubernetes/draft --namespace draft"
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

SERVICE="${1:-status}"
shift || true

case "$SERVICE" in
  status)
    do_status
    ;;

  ui)
    COMMAND="${1:-}"; shift || true
    # Parse ui-specific flags
    while [[ $# -gt 0 ]]; do
      case "$1" in
        -p) UI_PORT="$2"; shift ;;
        -p*) UI_PORT="${1#-p}" ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
      esac
      shift
    done
    case "$COMMAND" in
      start)   ui_start ;;
      stop)    ui_stop ;;
      restart) ui_restart ;;
      *) echo "Unknown command: $COMMAND"; usage; exit 1 ;;
    esac
    ;;

  mcp)
    COMMAND="${1:-}"; shift || true
    STDIO=0; LOG_JSON=0
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --stdio)    STDIO=1 ;;
        --log-json) LOG_JSON=1 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
      esac
      shift
    done
    case "$COMMAND" in
      start)
        if [ "$STDIO" -eq 1 ]; then mcp_start_stdio
        else mcp_start_http "$LOG_JSON"; fi
        ;;
      stop)    mcp_stop ;;
      restart) mcp_restart "$LOG_JSON" ;;
      logs)    mcp_logs ;;
      *) echo "Unknown command: $COMMAND"; usage; exit 1 ;;
    esac
    ;;

  -h|--help|help)
    usage
    ;;

  *)
    echo "Unknown service: $SERVICE"
    usage; exit 1
    ;;
esac
