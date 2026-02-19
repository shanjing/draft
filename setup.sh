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

# Always show the draft banner first
VIRTUAL_ENV="$SCRIPT_DIR/.venv" . "$SCRIPT_DIR/scripts/draft_banner.sh" 2>/dev/null || true

# Colors (MarginCall-style)
R='\033[0;31m'
G='\033[0;32m'
D='\033[0;90m'
N='\033[0m'

# --- First step: ensure .venv exists so pull.py (and deps) work during initial setup ---
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
  printf "${D}[1/2] Creating .venv${N}\n"
  python3 -m venv "$SCRIPT_DIR/.venv"
  printf "  ${G}✓${N} .venv created\n"
  bash "$SCRIPT_DIR/scripts/install_venv_banner.sh" 2>/dev/null || true
  printf "${D}[2/2] Installing dependencies${N}\n"
  "$SCRIPT_DIR/.venv/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"
  printf "  ${G}✓${N} requirements installed\n"
  echo ""
fi
PYTHON="${SCRIPT_DIR}/.venv/bin/python"

SOURCES_YAML="$SCRIPT_DIR/sources.yaml"
has_sources() {
  [ -f "$SOURCES_YAML" ] && grep -q "source:" "$SOURCES_YAML" 2>/dev/null
}

# Resolve user input to an absolute directory path and the path to pass to pull.py -a.
# For relative/bare names (e.g. MarginCall) tries ./, bare name, then ../ from project root.
# add_arg is always path-like (./, ../, or absolute) so pull.py stores the correct path.
resolve_source_path() {
  local input="$1"
  local resolved="" add_arg=""
  if [ -z "$input" ]; then
    return 1
  fi
  if [ -d "$input" ]; then
    resolved="$(cd "$input" 2>/dev/null && pwd)"
    add_arg="$input"
  else
    # Try from project root: ./, bare name, then ../
    for candidate in "./$input" "$input" "../$input"; do
      if (cd "$SCRIPT_DIR" 2>/dev/null && cd "$candidate" 2>/dev/null); then
        resolved="$(cd "$SCRIPT_DIR" && cd "$candidate" && pwd)"
        break
      fi
    done
  fi
  [ -n "$resolved" ] && [ -d "$resolved" ] || return 1
  # Compute path for pull.py: relative to project root so it stores correctly
  if [[ "$resolved" == "$SCRIPT_DIR"/* ]]; then
    add_arg="./${resolved#$SCRIPT_DIR/}"
  elif [[ "$resolved" == "$(dirname "$SCRIPT_DIR")"/* ]]; then
    add_arg="../${resolved#$(dirname "$SCRIPT_DIR")/}"
  else
    add_arg="$resolved"
  fi
  printf '%s\n' "$resolved"
  printf '%s\n' "$add_arg"
}

# Detect GitHub URL (https://github.com/... or git@github.com:...)
is_github_url() {
  case "$1" in
    https://github.com/*|http://github.com/*|git@github.com:*) return 0 ;;
    *) return 1 ;;
  esac
}

# Normalize GitHub URL to https form and extract owner/repo
parse_github_url() {
  local url="$1"
  local owner_repo=""
  if [ -z "$url" ]; then return 1; fi
  # https://github.com/owner/repo or https://github.com/owner/repo.git
  if [[ "$url" =~ ^https?://github\.com/([^/]+)/([^/]+) ]]; then
    owner_repo="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
  # git@github.com:owner/repo.git or git@github.com:owner/repo
  elif [[ "$url" =~ ^git@github\.com:([^/]+)/([^/]+) ]]; then
    owner_repo="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
  fi
  owner_repo="${owner_repo%.git}"
  [ -n "$owner_repo" ] || return 1
  printf 'https://github.com/%s\n' "$owner_repo"
  printf '%s\n' "$owner_repo"
}

# Validate GitHub repo exists and is reachable (git ls-remote)
validate_github_repo() {
  local url="$1"
  git ls-remote --exit-code "$url" HEAD 1>/dev/null 2>&1
}

# List current tracked sources from sources.yaml (name and source path)
list_tracked_sources() {
  [ ! -f "$SOURCES_YAML" ] && return
  if ! grep -q "source:" "$SOURCES_YAML" 2>/dev/null; then
    printf "${D}No sources tracked yet.${N}\n"
    return
  fi
  printf "${D}Current tracked sources:${N}\n"
  awk '
    /^[[:space:]]{2,}[A-Za-z0-9_.-]+[[:space:]]*:[[:space:]]*$/ {
      n = $1; gsub(/^[[:space:]]+|[[:space:]]*:[[:space:]]*$/, "", n);
      if (n != "repos" && n != "source") name = n;
      next;
    }
    /^[[:space:]]+source:[[:space:]]/ && name != "" {
      path = $0; gsub(/^[[:space:]]+source:[[:space:]]*/, "", path);
      printf "  - %s: %s\n", name, path;
      name = "";
      next;
    }
  ' "$SOURCES_YAML" 2>/dev/null
}

# Ensure sources.yaml exists and has at least "repos:" so pull.py and display work (best effort)
ensure_sources_yaml() {
  if [ ! -f "$SOURCES_YAML" ]; then
    printf '%s\n' "repos:" > "$SOURCES_YAML"
    return
  fi
  if [ ! -s "$SOURCES_YAML" ] || ! grep -q '^repos:' "$SOURCES_YAML" 2>/dev/null; then
    printf '%s\n' "repos:" > "$SOURCES_YAML"
  fi
}

# --- Managed sources: offer to add new sources ---
ensure_sources_yaml
read -r -p "Add new sources? (y/n): " add_sources
case "$add_sources" in
  [yY]|[yY][eE][sS])
    printf "\n"
    printf "Enter a local path (relative or absolute) or a GitHub repo URL.\n"
    printf "Press Enter when done adding.\n"
    echo ""

  while true; do
    read -r -p "Document source (path or GitHub URL; Enter when done): " src_path
    src_path="${src_path#"${src_path%%[![:space:]]*}"}"
    src_path="${src_path%"${src_path##*[![:space:]]}"}"
    if [ -z "$src_path" ]; then
      printf "\n"
      list_tracked_sources
      echo ""
      break
    fi

    # --- GitHub URL: add URL to sources.yaml; pull.py fetches .md via API (no clone) ---
    if is_github_url "$src_path"; then
      parsed="$(parse_github_url "$src_path")" || true
      if [ -z "$parsed" ]; then
        printf "  ${R}Invalid GitHub URL.${N}\n"
        continue
      fi
      https_url="$(echo "$parsed" | head -1)"
      owner_repo="$(echo "$parsed" | tail -1)"
      printf "  Checking GitHub repo: %s\n" "$owner_repo"
      if ! validate_github_repo "$https_url"; then
        printf "  ${R}Repo not found or not reachable.${N}\n"
        continue
      fi
      printf "  ${G}✓${N} Repo is reachable. .md files will be fetched from GitHub (no local clone).\n"
      echo ""
      read -r -p "Add this GitHub source? (y/n): " yn
      case "$yn" in
        [yY]|[yY][eE][sS])
          (cd "$SCRIPT_DIR" && "$PYTHON" scripts/pull.py -a "$src_path")
          printf "  ${G}✓${N} Added.\n"
          ;;
      esac
      echo ""
      continue
    fi

    # --- Local path (relative or absolute) ---
    resolve_out="$(resolve_source_path "$src_path")" || {
      printf "  ${R}Not found or not a directory: %s${N}\n" "$src_path"
      continue
    }
    resolved="$(echo "$resolve_out" | head -1)"
    add_arg="$(echo "$resolve_out" | tail -1)"
    md_count="$(find "$resolved" -name "*.md" -type f 2>/dev/null | wc -l | tr -d ' ')"
    printf "  Found: %s (%s .md file(s))\n" "$resolved" "$md_count"
    if [ -n "$md_count" ] && [ "$md_count" -gt 0 ]; then
      (cd "$SCRIPT_DIR" && "$PYTHON" scripts/pull.py -r "$resolved") 2>/dev/null | head -30 || true
    fi
    echo ""
    read -r -p "Add this source? (y/n): " yn
    case "$yn" in
      [yY]|[yY][eE][sS])
        (cd "$SCRIPT_DIR" && "$PYTHON" scripts/pull.py -a "$add_arg")
        printf "  ${G}✓${N} Added.\n"
        ;;
    esac
    echo ""
  done

    echo ""
    ;;
  *)
    ;;
esac
echo ""

check_venv() {
  [[ -d .venv ]]
}

printf "${D}--- Environment check ---${N}\n"
printf "  %b\n" "$(check_venv && echo "${G}✓${N} .venv exists" || echo "${R}✗${N} .venv missing")"
echo ""

printf "${G}✓ .venv ready.${N}\n"
bash "$SCRIPT_DIR/scripts/install_venv_banner.sh" 2>/dev/null || true
printf "${D}Activate with: source .venv/bin/activate${N}\n"
echo ""
read -r -p "Start the Draft UI? (y/n): " start_ui
case "$start_ui" in
  [yY]|[yY][eE][sS])
    ( sleep 2; case "$OS" in Darwin) open "http://localhost:8058" ;; *) xdg-open "http://localhost:8058" 2>/dev/null || true ;; esac ) &
    .venv/bin/python scripts/serve.py
    ;;
esac
