#!/bin/bash
# Draft UI: start, stop, or restart. Options: -p PORT, -s stop, -r restart.
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

PYTHON="${REPO_ROOT}/.venv/bin/python"
[ ! -x "$PYTHON" ] && PYTHON="python3"

PORT=8058
DO_STOP=0
DO_RESTART=0

while getopts "p:sr" opt; do
  case "$opt" in
    p) PORT="$OPTARG" ;;
    s) DO_STOP=1 ;;
    r) DO_RESTART=1 ;;
    *) exit 1 ;;
  esac
done

LOG_FILE="${DRAFT_HOME:-$REPO_ROOT}/.draft-ui.log"
PID_FILE="${DRAFT_HOME:-$REPO_ROOT}/.draft-ui.pid"

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
    echo "$pids" | xargs kill -9 2>/dev/null || true
    sleep 1
  fi
  if port_in_use; then
    if command -v fuser >/dev/null 2>&1; then
      fuser -k "${PORT}/tcp" 2>/dev/null || true
      sleep 1
    fi
  fi
}

stop_server() {
  if port_in_use; then
    kill_port
    echo "Stopped Draft UI on port $PORT."
  else
    echo "Nothing running on port $PORT."
  fi
  rm -f "$PID_FILE"
}

if [ "$DO_STOP" -eq 1 ]; then
  stop_server
  exit 0
fi

if [ "$DO_RESTART" -eq 1 ]; then
  stop_server
  sleep 1
fi

if [ "$DO_RESTART" -eq 0 ] && port_in_use; then
  echo "An instance is already running on port $PORT."
  read -r -p "Restart it? [y/N]: " ans
  ans="${ans:-n}"
  case "$ans" in
    [yY]|[yY][eE][sS])
      kill_port
      if port_in_use; then
        echo "Could not free port $PORT. Stop manually: ./draft.sh -s -p $PORT"
        exit 1
      fi
      ;;
    *)
      echo "Exiting. Start manually: $PYTHON scripts/serve.py -p $PORT"
      exit 0
      ;;
  esac
fi

echo "Starting Draft UI on port $PORT (daemon)..."
nohup "$PYTHON" "$REPO_ROOT/scripts/serve.py" -p "$PORT" >> "$LOG_FILE" 2>&1 &
PID=$!
echo $PID > "$PID_FILE"
echo "Draft UI started (PID $PID). Log: $LOG_FILE"
echo "Stop with: ./draft.sh -s -p $PORT  or  kill $PID"
sleep 3
case "$(uname -s)" in
  Darwin)   open "http://localhost:$PORT" ;;
  *)        xdg-open "http://localhost:$PORT" 2>/dev/null || true ;;
esac
