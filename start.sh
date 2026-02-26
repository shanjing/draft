#!/bin/bash
# Start the Draft UI. If something is already on port 8058, offer to restart (kill then start).
set -e

PORT="${1:-8058}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

PYTHON="${REPO_ROOT}/.venv/bin/python"
[ ! -x "$PYTHON" ] && PYTHON="python3"

# Check if port is in use (no lsof required: use Python socket)
port_in_use() {
  "$PYTHON" -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect(('127.0.0.1', $PORT))
    s.close()
    exit(0)   # something is listening
except (socket.error, OSError):
    exit(1)   # port free
" 2>/dev/null
}

# Get PIDs listening on port (lsof common on macOS/Linux; optional)
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
    echo "$pids" | xargs kill -9 2>/dev/null || true
    sleep 1
  fi
  # If still in use, try fuser (Linux)
  if port_in_use; then
    if command -v fuser >/dev/null 2>&1; then
      fuser -k "${PORT}/tcp" 2>/dev/null || true
      sleep 1
    fi
  fi
}

if port_in_use; then
  echo "An instance is already running on port $PORT."
  read -r -p "Restart it? [y/N]: " ans
  ans="${ans:-n}"
  case "$ans" in
    [yY]|[yY][eE][sS])
      kill_port
      if port_in_use; then
        echo "Could not free port $PORT. Stop the process manually and run this script again."
        exit 1
      fi
      ;;
    *)
      echo "Exiting. Start manually with: $PYTHON scripts/serve.py -p $PORT"
      exit 0
      ;;
  esac
fi

LOG_FILE="${DRAFT_HOME:-$REPO_ROOT}/.draft-ui.log"
PID_FILE="${DRAFT_HOME:-$REPO_ROOT}/.draft-ui.pid"

echo "Starting Draft UI on port $PORT (daemon)..."
nohup "$PYTHON" "$REPO_ROOT/scripts/serve.py" -p "$PORT" >> "$LOG_FILE" 2>&1 &
PID=$!
echo $PID > "$PID_FILE"
echo "Draft UI started (PID $PID). Log: $LOG_FILE"
echo "Stop with: kill $PID"
sleep 3
case "$(uname -s)" in
  Darwin)   open "http://localhost:$PORT" ;;
  *)       xdg-open "http://localhost:$PORT" 2>/dev/null || true ;;
esac
