#!/usr/bin/env bash
# Appends the draft activation banner to .venv/bin/activate.
# Run once after creating the virtual environment (e.g. after setup.sh or python3 -m venv .venv).
# Usage: ./scripts/install_venv_banner.sh   (from repo root)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ACTIVATE="$REPO_ROOT/.venv/bin/activate"

SENTINEL="# draft activation banner"

if [[ ! -f "$ACTIVATE" ]]; then
  echo "Not found: $ACTIVATE" >&2
  echo "Create the venv first, e.g.: python3 -m venv .venv" >&2
  exit 1
fi

if grep -q "$SENTINEL" "$ACTIVATE" 2>/dev/null; then
  exit 0
fi

# Append banner invocation (uses VIRTUAL_ENV set by activate to find project root)
{
  echo ""
  echo "$SENTINEL"
  echo "if [ -n \"\${VIRTUAL_ENV:-}\" ] && [ -f \"\$(dirname \"\$VIRTUAL_ENV\")/scripts/draft_banner.sh\" ]; then"
  echo "  . \"\$(dirname \"\$VIRTUAL_ENV\")/scripts/draft_banner.sh\""
  echo "fi"
} >> "$ACTIVATE"
