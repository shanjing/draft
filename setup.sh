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

# Recreate .venv if requested (use after installing Python 3.12/3.11 to replace 3.14 venv)
RECREATE_VENV=
[ "${1:-}" = "--recreate" ] && RECREATE_VENV=1 && shift

# Always show the draft banner first
VIRTUAL_ENV="$SCRIPT_DIR/.venv" . "$SCRIPT_DIR/scripts/draft_banner.sh" 2>/dev/null || true

# Colors (MarginCall-style)
R='\033[0;31m'
G='\033[0;32m'
D='\033[0;90m'
N='\033[0m'

# Prefer Python 3.12 or 3.11 for ChromaDB/sentence-transformers (3.14 not supported)
find_python() {
  for py in python3.12 python3.11 python3; do
    if command -v "$py" >/dev/null 2>&1; then
      ver=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
      if [ -n "$ver" ]; then
        # Prefer 3.11 or 3.12; allow 3.9+ for older systems
        if printf '%s\n' "$ver" | grep -qE '^3\.(9|10|11|12)$'; then
          echo "$py"
          return
        fi
        if [ "$py" = "python3" ] && printf '%s\n' "$ver" | grep -qE '^3\.1[4-9]'; then
          printf "${R}Warning: Python %s is not compatible with ChromaDB (Ask AI). Install Python 3.12 or 3.11 and re-run.${N}\n" "$ver" >&2
        fi
        [ "$py" = "python3" ] && echo "$py" && return
      fi
    fi
  done
  echo "python3"
}

if [ -n "$RECREATE_VENV" ] && [ -d "$SCRIPT_DIR/.venv" ]; then
  printf "${D}Removing existing .venv (--recreate)${N}\n"
  rm -rf "$SCRIPT_DIR/.venv"
fi

# --- First step: ensure .venv exists with a compatible Python ---
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
  PYEXE=$(find_python)
  printf "${D}[1/2] Creating .venv with %s${N}\n" "$PYEXE"
  "$PYEXE" -m venv "$SCRIPT_DIR/.venv"
  printf "  ${G}✓${N} .venv created\n"
  bash "$SCRIPT_DIR/scripts/install_venv_banner.sh" 2>/dev/null || true
  printf "${D}[2/2] Installing dependencies${N}\n"
  "$SCRIPT_DIR/.venv/bin/pip" install --progress-bar on -r "$SCRIPT_DIR/requirements.txt"
  printf "  ${G}✓${N} requirements installed\n"
  echo ""
fi
PYTHON="${SCRIPT_DIR}/.venv/bin/python"

# User data and config: DRAFT_HOME defaults to ~/.draft; sources.yaml lives there
DRAFT_HOME="${DRAFT_HOME:-$HOME/.draft}"
export DRAFT_HOME
mkdir -p "$DRAFT_HOME"
SOURCES_YAML="$DRAFT_HOME/sources.yaml"
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

# Return 0 if repo name is already in sources.yaml (so we can skip add and avoid error)
source_already_tracked() {
  local name="$1"
  [ ! -f "$SOURCES_YAML" ] && return 1
  awk -v n="$name" '
    /^[[:space:]]{2,}[A-Za-z0-9_.-]+[[:space:]]*:[[:space:]]*$/ {
      gsub(/^[[:space:]]+/, ""); gsub(/[[:space:]]*:[[:space:]]*$/, ""); if ($0 == n) found=1
    }
    END { exit (found ? 0 : 1) }
  ' "$SOURCES_YAML" 2>/dev/null
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

# Ensure sources.yaml exists in DRAFT_HOME: copy from repo sources.example.yaml if missing
ensure_sources_yaml() {
  if [ ! -f "$SOURCES_YAML" ]; then
    if [ -f "$SCRIPT_DIR/sources.example.yaml" ]; then
      cp "$SCRIPT_DIR/sources.example.yaml" "$SOURCES_YAML"
      printf "${G}Created %s from sources.example.yaml (edit to add your doc sources).${N}\n" "$SOURCES_YAML"
    else
      printf '%s\n' "repos:" > "$SOURCES_YAML"
    fi
    return
  fi
  if [ ! -s "$SOURCES_YAML" ] || ! grep -q '^repos:' "$SOURCES_YAML" 2>/dev/null; then
    if [ -f "$SCRIPT_DIR/sources.example.yaml" ]; then
      cp "$SCRIPT_DIR/sources.example.yaml" "$SOURCES_YAML"
    else
      printf '%s\n' "repos:" > "$SOURCES_YAML"
    fi
  fi
}

# --- Managed sources: offer to add new sources ---
ensure_sources_yaml
# Verify sources.yaml before reading it (mandatory: fail if invalid)
if ! (cd "$SCRIPT_DIR" && "$PYTHON" scripts/verify_sources.py -r "$SCRIPT_DIR" -q 2>/dev/null); then
  printf "${R}sources.yaml is invalid. Fix errors and re-run setup. Run: %s scripts/verify_sources.py -r %s${N}\n" "$PYTHON" "$SCRIPT_DIR" >&2
  (cd "$SCRIPT_DIR" && "$PYTHON" scripts/verify_sources.py -r "$SCRIPT_DIR" 2>&1) || true
  exit 1
fi
read -r -p "Add new sources? (y/n): " add_sources
case "$add_sources" in
  [yY]|[yY][eE][sS])
    export DRAFT_SETUP=1
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
      if source_already_tracked "$owner_repo"; then
        printf "  ${D}%s is already in sources.yaml.${N}\n" "$owner_repo"
        echo ""
        continue
      fi
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
    repo_name="$(basename "$resolved")"
    if source_already_tracked "$repo_name"; then
      printf "  ${D}%s is already in sources.yaml.${N}\n" "$repo_name"
      echo ""
      continue
    fi
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

# Verify API keys (read-only endpoints). Return 0 if valid.
verify_anthropic_key() {
  local key="$1"
  [ -z "$key" ] && return 1
  key="$(printf '%s' "$key" | tr -d '\n\r')"
  [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 -X GET "https://api.anthropic.com/v1/models" -H "x-api-key: ${key}" -H "anthropic-version: 2023-06-01" -H "Content-Type: application/json" 2>/dev/null)" = "200" ]
}
verify_gemini_key() {
  local key="$1"
  [ -z "$key" ] && return 1
  key="$(printf '%s' "$key" | tr -d '\n\r')"
  [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "https://generativelanguage.googleapis.com/v1beta/models?key=${key}" 2>/dev/null)" = "200" ]
}
verify_openai_key() {
  local key="$1"
  [ -z "$key" ] && return 1
  key="$(printf '%s' "$key" | tr -d '\n\r')"
  [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 -X GET "https://api.openai.com/v1/models" -H "Authorization: Bearer ${key}" 2>/dev/null)" = "200" ]
}

# --- Optional: Ask (AI) LLM configuration ---
read -r -p "Configure Ask (AI) LLM? (y/n): " config_llm
case "$config_llm" in
  [yY]|[yY][eE][sS])
    echo ""
    env_file="$SCRIPT_DIR/.env"
    llm_start=10
    # Build Ollama list (indices 1..N) if available
    OLLAMA_NAMES=()
    if command -v ollama >/dev/null 2>&1; then
      while IFS= read -r name; do
        [ -n "$name" ] && OLLAMA_NAMES+=("$name")
      done < <(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}')
      idx=1
      for name in "${OLLAMA_NAMES[@]}"; do
        printf "  ${G}%d.${N} %s (Ollama)\n" "$idx" "$name"
        idx=$((idx + 1))
      done
      llm_start=$idx
    else
      printf "${D}(Ollama not installed — local models skipped)${N}\n"
    fi
    first_ollama=1
    last_ollama=$((llm_start - 1))
    # Cloud and Other (fixed indices 10, 11, 12, 13 — or next available)
    printf "  ${G}%d.${N} Gemini 2.5 Flash (cloud)\n" "$llm_start"
    num_gemini=$llm_start
    num_opus=$((llm_start + 1))
    num_openai=$((llm_start + 2))
    num_other=$((llm_start + 3))
    printf "  ${G}%d.${N} Opus / Claude (cloud)\n" "$num_opus"
    printf "  ${G}%d.${N} OpenAI low (cloud)\n" "$num_openai"
    printf "  ${G}%d.${N} Other (enter model string)\n" "$num_other"
    echo ""
    max_choice=$num_other

    while true; do
      read -r -p "Choose model (1-${max_choice}): " choice
      choice="$(printf '%s' "$choice" | tr -d '\n\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      if [ -z "$choice" ]; then
        printf "${D}Skipped.${N}\n"
        break
      fi
      if [ "$choice" -ge "$first_ollama" ] 2>/dev/null && [ "$choice" -le "$last_ollama" ] 2>/dev/null; then
        # Ollama
        i=$((choice - 1))
        model_name="${OLLAMA_NAMES[i]:-}"
        if [ -n "$model_name" ]; then
          (cd "$SCRIPT_DIR" && "$PYTHON" scripts/setup_env_writer.py --mode ollama --model "$model_name")
          printf "  ${G}✓${N} Set .env: Ollama model %s\n" "$model_name"
          break
        fi
        printf "  ${R}No model at that index.${N}\n"
      elif [ "$choice" = "$num_gemini" ]; then
        read -r -s -p "Enter Gemini API key: " api_key
        echo ""
        api_key="$(printf '%s' "$api_key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        if [ -z "$api_key" ]; then
          printf "${D}Skipped.${N}\n"
          break
        fi
        printf "${D}Verifying...${N}\n"
        if verify_gemini_key "$api_key"; then
          (cd "$SCRIPT_DIR" && "$PYTHON" scripts/setup_env_writer.py --mode gemini --model "gemini-2.5-flash" --api-key "$api_key")
          printf "  ${G}✓${N} Key valid. .env updated for Gemini 2.5 Flash.\n"
          break
        else
          printf "  ${R}Invalid key.${N}\n"
        fi
      elif [ "$choice" = "$num_opus" ]; then
        read -r -s -p "Enter Anthropic API key: " api_key
        echo ""
        api_key="$(printf '%s' "$api_key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        if [ -z "$api_key" ]; then
          printf "${D}Skipped.${N}\n"
          break
        fi
        printf "${D}Verifying...${N}\n"
        if verify_anthropic_key "$api_key"; then
          (cd "$SCRIPT_DIR" && "$PYTHON" scripts/setup_env_writer.py --mode claude --model "claude-3-opus-20240229" --api-key "$api_key")
          printf "  ${G}✓${N} Key valid. .env updated for Opus (Claude).\n"
          break
        else
          printf "  ${R}Invalid key.${N}\n"
        fi
      elif [ "$choice" = "$num_openai" ]; then
        read -r -s -p "Enter OpenAI API key: " api_key
        echo ""
        api_key="$(printf '%s' "$api_key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        if [ -z "$api_key" ]; then
          printf "${D}Skipped.${N}\n"
          break
        fi
        printf "${D}Verifying...${N}\n"
        if verify_openai_key "$api_key"; then
          (cd "$SCRIPT_DIR" && "$PYTHON" scripts/setup_env_writer.py --mode openai --model "gpt-4o-mini" --api-key "$api_key")
          printf "  ${G}✓${N} Key valid. .env updated for OpenAI.\n"
          break
        else
          printf "  ${R}Invalid key.${N}\n"
        fi
      elif [ "$choice" = "$num_other" ]; then
        read -r -p "Enter model name (e.g. ollama model or provider:model): " other_model
        other_model="$(printf '%s' "$other_model" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        if [ -z "$other_model" ]; then
          printf "${D}Skipped.${N}\n"
          break
        fi
        (cd "$SCRIPT_DIR" && "$PYTHON" scripts/setup_env_writer.py --mode ollama --model "$other_model")
        printf "  ${G}✓${N} Set .env: custom model %s (Ollama).\n" "$other_model"
        break
      else
        printf "  ${R}Enter a number 1-%s.${N}\n" "$max_choice"
      fi
    done
    echo ""
    ;;
  *) ;;
esac

printf "${G}✓ .venv ready.${N}\n"
bash "$SCRIPT_DIR/scripts/install_venv_banner.sh" 2>/dev/null || true
printf "${D}Activate with: source .venv/bin/activate${N}\n"
echo ""

# Build RAG/vector index if a valid LLM is configured; ask user first
if (cd "$SCRIPT_DIR" && "$PYTHON" scripts/check_llm_ready.py 2>/dev/null); then
  while true; do
    read -r -p "RAG/index is required to use the AI feature, do you want to build it now? You can always build it in the UI later. (y/n): " build_rag
    build_rag="$(printf '%s' "$build_rag" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    case "$build_rag" in
      y|yes) build_rag=1; break ;;
      n|no)  build_rag=0; break ;;
      *)     printf "  ${D}Please answer y or n.${N}\n" ;;
    esac
  done
  if [ "$build_rag" = "1" ]; then
    rag_profile="quick"
    while true; do
      read -r -p "Choose RAG/index rebuild mode: quick (faster, lighter model) or deep (nomic, slower). [quick/deep]: " rag_profile
      rag_profile="$(printf '%s' "$rag_profile" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      case "$rag_profile" in
        quick|q|"") rag_profile="quick"; break ;;
        deep|d)      rag_profile="deep"; break ;;
        *)           printf "  ${D}Please answer quick or deep.${N}\n" ;;
      esac
    done
    printf "${D}Build RAG/vector index ...${N}\n"
    # Ensure numpy<2 (and other deps) so index build doesn't fail with NumPy 2.x incompatibility
    "$SCRIPT_DIR/.venv/bin/pip" install --progress-bar on -r "$SCRIPT_DIR/requirements.txt" 2>/dev/null || true
    if (cd "$SCRIPT_DIR" && "$PYTHON" scripts/index_for_ai.py --profile "$rag_profile" -v); then
      printf "${G}done.${N}\n"
    else
      printf "${R}failed (Ask index not built).${N}\n" >&2
    fi
  fi
fi
echo ""
read -r -p "Start the Draft UI? (y/n): " start_ui
case "$start_ui" in
  [yY]|[yY][eE][sS])
    _UI_LOG="${SCRIPT_DIR}/.draft-ui.log"
    nohup "$PYTHON" "$SCRIPT_DIR/scripts/serve.py" >> "$_UI_LOG" 2>&1 &
    _UI_PID=$!
    ( sleep 2; case "$OS" in Darwin) open "http://localhost:8058" ;; *) xdg-open "http://localhost:8058" 2>/dev/null || true ;; esac ) &
    printf "  ${G}Draft UI started in background${N} (PID %s). Log: %s\n" "$_UI_PID" "$_UI_LOG"
    printf "  ${D}Stop with: kill %s${N}\n" "$_UI_PID"
    ;;
esac
