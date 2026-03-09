#!/bin/bash
# Draft MCP server: start, stop, restart, status, logs.
# Usage: ./draft_mcp.sh [start|stop|restart|status|logs] [--stdio] [--log-json] [-p PORT]
#
# Modes:
#   start            Start HTTP daemon on PORT (default 8059), background
#   start --stdio    Run stdio transport in foreground (for Claude Desktop or piped use)
#   stop             Stop the HTTP daemon
#   restart          Stop then start the HTTP daemon
#   status           Show whether the daemon is running and its health
#   logs             Tail ~/.draft/draft-mcp.log
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

PYTHON="${REPO_ROOT}/.venv/bin/python"
[ ! -x "$PYTHON" ] && PYTHON="python3"

# Defaults
COMMAND="${1:-start}"
PORT=8059
STDIO=0
LOG_JSON=0
DRAFT_HOME_OVERRIDE=""

# Shift past the command
shift 2>/dev/null || true

# Parse remaining flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --stdio)     STDIO=1 ;;
    --log-json)  LOG_JSON=1 ;;
    -p)          PORT="$2"; shift ;;
    -p*)         PORT="${1#-p}" ;;
    --draft-home) DRAFT_HOME_OVERRIDE="$2"; shift ;;
    *)           echo "Unknown option: $1"; exit 1 ;;
  esac
  shift
done

# Resolve DRAFT_HOME
if [ -n "$DRAFT_HOME_OVERRIDE" ]; then
  DRAFT_HOME="$DRAFT_HOME_OVERRIDE"
elif [ -z "$DRAFT_HOME" ]; then
  DRAFT_HOME="$HOME/.draft"
fi
export DRAFT_HOME

LOG_FILE="${DRAFT_HOME}/draft-mcp.log"
PID_FILE="${DRAFT_HOME}/draft-mcp.pid"

# Build the python command args
build_args() {
  local args=("$REPO_ROOT/scripts/serve_mcp.py")
  [ "$STDIO" -eq 1 ]    && args+=("--stdio")
  [ "$LOG_JSON" -eq 1 ] && args+=("--log-json")
  echo "${args[@]}"
}

# ── Port helpers ────────────────────────────────────────────────────────────

port_in_use() {
  "$PYTHON" -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect(('127.0.0.1', $PORT))
    s.close()
    exit(0)
except (socket.error, OSError):
    exit(1)
" 2>/dev/null
}

pids_on_port() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti ":$PORT" 2>/dev/null || true
  else
    echo ""
  fi
}

kill_port() {
  local pids
  pids=$(pids_on_port)
  if [ -n "$pids" ]; then
    echo "$pids" | xargs kill -TERM 2>/dev/null || true
    sleep 1
  fi
  # Fallback: fuser
  if port_in_use && command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" 2>/dev/null || true
    sleep 1
  fi
}

# ── PID helpers ─────────────────────────────────────────────────────────────

read_pid() {
  [ -f "$PID_FILE" ] && cat "$PID_FILE" || echo ""
}

pid_alive() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

# ── Health check ─────────────────────────────────────────────────────────────

health_check() {
  if command -v curl >/dev/null 2>&1; then
    curl -sf "http://127.0.0.1:${PORT}/health" 2>/dev/null || true
  fi
}

# ── Commands ─────────────────────────────────────────────────────────────────

do_stop() {
  local pid
  pid=$(read_pid)

  if pid_alive "$pid"; then
    kill -TERM "$pid" 2>/dev/null || true
    sleep 1
    if pid_alive "$pid"; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
    echo "Stopped Draft MCP server (PID $pid)."
  elif port_in_use; then
    kill_port
    echo "Stopped Draft MCP server on port $PORT."
  else
    echo "Draft MCP server is not running."
  fi

  rm -f "$PID_FILE"
}

do_start_http() {
  local pid
  pid=$(read_pid)

  if pid_alive "$pid"; then
    echo "Draft MCP server is already running (PID $pid, port $PORT)."
    echo "Use './draft_mcp.sh restart' to restart it."
    exit 0
  fi

  if port_in_use; then
    echo "Port $PORT is already in use by another process."
    read -r -p "Kill it and start fresh? [y/N]: " ans
    ans="${ans:-n}"
    case "$ans" in
      [yY]|[yY][eE][sS]) kill_port ;;
      *) echo "Exiting."; exit 0 ;;
    esac
  fi

  mkdir -p "$DRAFT_HOME"

  local extra_env=""
  [ "$LOG_JSON" -eq 1 ] && extra_env="MCP_LOG_JSON=1 "

  echo "Starting Draft MCP server (HTTP, port $PORT)..."
  # shellcheck disable=SC2086
  eval "DRAFT_HOME='$DRAFT_HOME' ${extra_env}nohup '$PYTHON' '$REPO_ROOT/scripts/serve_mcp.py' >> '$LOG_FILE' 2>&1" &
  local PID=$!
  echo $PID > "$PID_FILE"

  # Give it a moment to start, then verify
  sleep 2
  if pid_alive "$PID"; then
    echo "Draft MCP server started (PID $PID, port $PORT)."
    local health
    health=$(health_check)
    [ -n "$health" ] && echo "Health: $health"
    echo "Log:  $LOG_FILE"
    echo "Stop: ./draft_mcp.sh stop"
  else
    echo "Server failed to start. Check the log:"
    tail -20 "$LOG_FILE" 2>/dev/null || true
    rm -f "$PID_FILE"
    exit 1
  fi
}

do_start_stdio() {
  echo "Starting Draft MCP server (stdio, foreground)..."
  echo "Logs → $LOG_FILE"
  local args
  args=($(build_args))
  # shellcheck disable=SC2068
  exec "$PYTHON" ${args[@]}
}

do_status() {
  local pid
  pid=$(read_pid)

  echo "=== Draft MCP Server Status ==="
  echo "DRAFT_HOME : $DRAFT_HOME"
  echo "Port       : $PORT"
  echo "PID file   : $PID_FILE"
  echo "Log file   : $LOG_FILE"
  echo ""

  if pid_alive "$pid"; then
    echo "State  : RUNNING (PID $pid)"
    local health
    health=$(health_check)
    if [ -n "$health" ]; then
      echo "Health : $health"
    else
      echo "Health : (no response on port $PORT — server may still be starting)"
    fi
  elif port_in_use; then
    echo "State  : port $PORT in use (no PID file — started outside this script)"
    local health
    health=$(health_check)
    [ -n "$health" ] && echo "Health : $health"
  else
    echo "State  : STOPPED"
  fi

  echo ""
  if [ -f "$LOG_FILE" ]; then
    echo "--- Last 5 log lines ---"
    tail -5 "$LOG_FILE"
  fi
}

do_logs() {
  if [ ! -f "$LOG_FILE" ]; then
    echo "No log file yet: $LOG_FILE"
    echo "Start the server first: ./draft_mcp.sh start"
    exit 1
  fi
  echo "Tailing $LOG_FILE  (Ctrl-C to stop)"
  tail -f "$LOG_FILE"
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

case "$COMMAND" in
  start)
    if [ "$STDIO" -eq 1 ]; then
      do_start_stdio
    else
      do_start_http
    fi
    ;;
  stop)
    do_stop
    ;;
  restart)
    do_stop
    sleep 1
    do_start_http
    ;;
  status)
    do_status
    ;;
  logs)
    do_logs
    ;;
  *)
    echo "Usage: $0 [start|stop|restart|status|logs] [--stdio] [--log-json] [-p PORT] [--draft-home PATH]"
    echo ""
    echo "  start              Start HTTP daemon (background, port $PORT)"
    echo "  start --stdio      Run stdio transport (foreground)"
    echo "  start --log-json   Start HTTP daemon with JSON log format"
    echo "  stop               Stop the HTTP daemon"
    echo "  restart            Stop then start the HTTP daemon"
    echo "  status             Show running state and health"
    echo "  logs               Tail ~/.draft/draft-mcp.log"
    exit 1
    ;;
esac
