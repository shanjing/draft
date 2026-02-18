#!/bin/bash
# Setup script for draft: create .venv, install deps, install activation banner.
# On Windows, create .venv manually and run: .venv\Scripts\pip install -r requirements.txt
set -e

OS="$(uname -s)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

case "$OS" in
  MINGW*|MSYS*|CYGWIN*)
    echo "On Windows, create the venv manually: python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt"
    exit 1
    ;;
esac

# Colors (MarginCall-style)
R='\033[0;31m'
G='\033[0;32m'
D='\033[0;90m'
N='\033[0m'

check_venv() {
  [[ -d .venv ]]
}

echo ""
printf "${D}draft — private doc store from tracked repos${N}\n"
echo ""
printf "${D}--- Environment check ---${N}\n"
printf "  %b\n" "$(check_venv && echo "${G}✓${N} .venv exists" || echo "${R}✗${N} .venv missing")"
echo ""

if check_venv; then
  printf "${G}✓ .venv already exists.${N}\n"
  bash "$SCRIPT_DIR/scripts/install_venv_banner.sh" 2>/dev/null || true
  printf "${D}Activate with: source .venv/bin/activate${N}\n"
  exit 0
fi

# Create .venv (use python3 from PATH)
printf "${D}[1/2] Creating .venv${N}\n"
python3 -m venv .venv
printf "  ${G}✓${N} .venv created\n"

# Install activation banner so "source .venv/bin/activate" shows draft block-art
bash "$SCRIPT_DIR/scripts/install_venv_banner.sh" 2>/dev/null || true

# Install dependencies
printf "${D}[2/2] Installing dependencies${N}\n"
source .venv/bin/activate
pip install -q -r requirements.txt
printf "  ${G}✓${N} requirements installed\n"
echo ""

printf "${G}✓ Setup complete.${N}\n"
printf "${D}Activate with: source .venv/bin/activate${N}\n"
echo ""
