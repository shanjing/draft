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
Y='\033[1;33m'
D='\033[0;90m'
N='\033[0m'

# Pick requirements file by host: Intel Mac (Darwin x86_64) uses requirements-intel-mac.txt (torch 2.2 + older transformers).
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"
pick_requirements_file() {
  local os arch
  os="$(uname -s)"
  arch="$(uname -m)"
  if [ "$os" = "Darwin" ] && [ "$arch" = "x86_64" ]; then
    REQUIREMENTS_FILE="$SCRIPT_DIR/requirements-intel-mac.txt"
  else
    REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"
  fi
}
pick_requirements_file

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
  printf "${D}[2/2] Installing dependencies (%s)${N}\n" "$(basename "$REQUIREMENTS_FILE")"
  "$SCRIPT_DIR/.venv/bin/pip" install --progress-bar on -r "$REQUIREMENTS_FILE"
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

# Collect repo names from sources.yaml (names that have a source: line). One per line.
list_repo_names_in_yaml() {
  [ ! -f "$SOURCES_YAML" ] && return
  awk '
    /^[[:space:]]{2,}[A-Za-z0-9_.-]+[[:space:]]*:[[:space:]]*$/ {
      n = $1; gsub(/^[[:space:]]+|[[:space:]]*:[[:space:]]*$/, "", n);
      if (n != "repos" && n != "source") name = n;
      next;
    }
    /^[[:space:]]+source:[[:space:]]/ && name != "" {
      print name;
      name = "";
      next;
    }
  ' "$SOURCES_YAML" 2>/dev/null
}

# Output "name<TAB>source" per repo (for consistency check: GitHub -> .clones, local -> path).
list_repos_name_and_source() {
  [ ! -f "$SOURCES_YAML" ] && return
  awk '
    /^[[:space:]]{2,}[A-Za-z0-9_.-]+[[:space:]]*:[[:space:]]*$/ {
      n = $1; gsub(/^[[:space:]]+|[[:space:]]*:[[:space:]]*$/, "", n);
      if (n != "repos" && n != "source") name = n;
      next;
    }
    /^[[:space:]]+source:[[:space:]]/ && name != "" {
      src = $0; gsub(/^[[:space:]]+source:[[:space:]]*/, "", src);
      print name "\t" src;
      name = "";
      next;
    }
  ' "$SOURCES_YAML" 2>/dev/null
}

# Make sources.yaml follow actual content: add entries for vault (if dir exists) and for each
# .doc_sources subdir that is not in sources.yaml. True source of truth for content is disk;
# sources.yaml is source of truth only among config files.
sync_sources_yaml_from_content() {
  [ ! -f "$SOURCES_YAML" ] && return
  local added=0
  # Ensure vault entry exists when vault dir exists
  if [ -d "$DRAFT_HOME/vault" ] && ! list_repo_names_in_yaml | grep -Fxq "vault" 2>/dev/null; then
    printf "  ${D}Adding vault to sources.yaml (vault dir exists).${N}\n"
    printf '\n  vault:\n    source: ./vault\n' >> "$SOURCES_YAML"
    added=1
  fi
  # Add each .doc_sources subdir that is not in sources.yaml (use absolute path so pull resolves correctly)
  if [ -d "$DRAFT_HOME/.doc_sources" ]; then
    for subdir in "$DRAFT_HOME/.doc_sources"/*/; do
      [ -d "$subdir" ] || continue
      name="$(basename "$subdir")"
      if list_repo_names_in_yaml | grep -Fxq "$name" 2>/dev/null; then
        continue
      fi
      printf "  ${D}Adding %s to sources.yaml (.doc_sources/%s exists).${N}\n" "$name" "$name"
      printf '\n  %s:\n    source: %s/.doc_sources/%s\n' "$name" "$DRAFT_HOME" "$name" >> "$SOURCES_YAML"
      added=1
    done
  fi
  if [ "$added" = "1" ]; then
    printf "${D}sources.yaml updated to match on-disk content.${N}\n"
  fi
}

# Check consistency between sources.yaml and disk. Warn only when yaml lists something missing.
# GitHub repos: content in .clones/<name>. Local: content at source path (no .doc_sources copy).
check_sources_consistency() {
  [ ! -f "$SOURCES_YAML" ] && return
  local name source resolved
  local warnings=0
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    name="${line%%$'\t'*}"
    source="${line#*$'\t'}"
    source="$(printf '%s' "$source" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    if [ "$name" = "vault" ]; then
      if [ ! -d "$DRAFT_HOME/vault" ]; then
        printf "  ${D}%s: vault listed in sources.yaml but %s/vault not found (create dir).${N}\n" "$name" "$DRAFT_HOME"
        warnings=1
      fi
    elif [ -n "$source" ] && [[ "$source" == *github.com* ]]; then
      if [ ! -d "$DRAFT_HOME/.clones/$name" ]; then
        printf "  ${D}%s: listed in sources.yaml but %s/.clones/%s not found (run Pull).${N}\n" "$name" "$DRAFT_HOME" "$name"
        warnings=1
      fi
    else
      if [ -n "$source" ]; then
        case "$source" in
          /*) resolved="$source" ;;
          *)  resolved="$SCRIPT_DIR/$source" ;;
        esac
        if [ ! -d "$resolved" ]; then
          printf "  ${D}%s: listed in sources.yaml but path not found: %s (run Pull or fix path).${N}\n" "$name" "$resolved"
          warnings=1
        fi
      fi
    fi
  done < <(list_repos_name_and_source)
  if [ "$warnings" = "1" ]; then
    printf "${D}Consistency: see warnings above.${N}\n"
  else
    printf "${D}Consistency: OK.${N}\n"
  fi
}

# Show Actions (required/suggested/None) in yellow. Called after consistency check.
# Uses RAG index (Chroma) value as baseline; if current configured model differs, [required] rebuild.
show_actions() {
  local baseline_embed current_embed has_required=0 has_suggested=0
  # Baseline = what the index was built with (same as "RAG index:" in current state)
  baseline_embed=""
  if [ -d "$DRAFT_HOME/.vector_store" ] && [ -n "$(find "$DRAFT_HOME/.vector_store" -type f 2>/dev/null | head -1)" ]; then
    baseline_embed=$(cd "$SCRIPT_DIR" && "$PYTHON" -c "
import sys
sys.path.insert(0, '.')
try:
    import chromadb
    from chromadb.config import Settings
    from lib.paths import get_vector_store_root
    from lib.ingest import COLLECTION_NAME
    client = chromadb.PersistentClient(path=str(get_vector_store_root()), settings=Settings(anonymized_telemetry=False))
    col = client.get_collection(COLLECTION_NAME)
    meta = getattr(col, 'metadata', None) or {}
    print(meta.get('embed_model') or meta.get('profile', '') or '')
except Exception:
    print('')
" 2>/dev/null) || true
  fi
  # Current model = what would be used for next build (same as "Embed:" in current state)
  current_embed="$(env_val "DRAFT_EMBED_MODEL" "$DEFAULT_EMBED_MODEL")"
  [ -z "$current_embed" ] && current_embed="$DEFAULT_EMBED_MODEL"
  printf "${D}Actions:${N}\n"
  if [ -n "$baseline_embed" ] && [ "$current_embed" != "$baseline_embed" ]; then
    printf "  ${Y}[required] Rebuild the index with the new model in step 5 (Build RAG/index).${N}\n"
    printf "  ${Y}[reason] The current Embed model is %s does not match RAG index (%s).${N}\n" "$current_embed" "$baseline_embed"
    has_required=1
  fi
  # Suggest build when no index AND (doc_sources or vault has indexable content)
  if [ -z "$baseline_embed" ]; then
    _has_content=0
    [ -d "$DRAFT_HOME/.doc_sources" ] && [ -n "$(find "$DRAFT_HOME/.doc_sources" -mindepth 2 -type f 2>/dev/null | head -1)" ] && _has_content=1
    [ -d "$DRAFT_HOME/vault" ] && [ -n "$(find "$DRAFT_HOME/vault" -type f 2>/dev/null | head -1)" ] && _has_content=1
    if [ "$_has_content" -eq 1 ]; then
      printf "  ${Y}[suggested] Build the RAG index in step 5 (Build RAG/index).${N}\n"
      has_suggested=1
    fi
    unset _has_content
  fi
  # Embed/encoder/LLM: required when .env missing or value not set
  _emb_val="$(env_val "DRAFT_EMBED_MODEL" "")"
  _enc_val="$(env_val "DRAFT_CROSS_ENCODER_MODEL" "")"
  if [ -z "$_emb_val" ]; then
    printf "  ${Y}[required] Set embedding model in step 2 (Setup embedding model).${N}\n"
    has_required=1
  fi
  if [ -z "$_enc_val" ]; then
    printf "  ${Y}[required] Set encoder model in step 3 (Setup encoder model).${N}\n"
    has_required=1
  fi
  unset _emb_val _enc_val
  _llm_ok=0
  if [ -f "$SCRIPT_DIR/.env" ]; then
    _lp=$(grep -E '^[[:space:]]*DRAFT_LLM_PROVIDER[[:space:]]*=' "$SCRIPT_DIR/.env" 2>/dev/null | sed -E "s/^[^=]*=[[:space:]]*['\"]?//;s/['\"]?[[:space:]]*$//" | head -1)
    _lm=$(grep -E '^[[:space:]]*OLLAMA_MODEL[[:space:]]*=' "$SCRIPT_DIR/.env" 2>/dev/null | sed -E "s/^[^=]*=[[:space:]]*['\"]?//;s/['\"]?[[:space:]]*$//" | head -1)
    [ -z "$_lm" ] && _lm=$(grep -E '^[[:space:]]*DRAFT_LLM_MODEL[[:space:]]*=' "$SCRIPT_DIR/.env" 2>/dev/null | sed -E "s/^[^=]*=[[:space:]]*['\"]?//;s/['\"]?[[:space:]]*$//" | head -1)
    [ -n "$_lp" ] && _llm_ok=1
    [ -n "$_lm" ] && _llm_ok=1
    for _k in ANTHROPIC_API_KEY GEMINI_API_KEY OPENAI_API_KEY; do
      _v=$(grep -E "^[[:space:]]*${_k}[[:space:]]*=" "$SCRIPT_DIR/.env" 2>/dev/null | sed -E "s/^[^=]*=[[:space:]]*['\"]?//;s/['\"]?[[:space:]]*$//" | head -1)
      [ -n "$_v" ] && _llm_ok=1
    done
    unset _lp _lm _k _v
  fi
  if [ "$_llm_ok" -eq 0 ]; then
    printf "  ${Y}[required] Configure LLM in step 4 (Configure LLM).${N}\n"
    has_required=1
  fi
  unset _llm_ok
  if [ "$has_required" = "0" ] && [ "$has_suggested" = "0" ]; then
    printf "  ${Y}[None] You are good to go.${N}\n"
  fi
}

# Show current state for existing install: sources, vault file count, LLM config.
show_current_state() {
  printf "${D}--- Current state ---${N}\n"
  list_tracked_sources
  local vault_count=0
  [ -d "$DRAFT_HOME/vault" ] && vault_count="$(find "$DRAFT_HOME/vault" -type f 2>/dev/null | wc -l | tr -d ' ')"
  printf "  ${D}Vault: %s file(s)${N}\n" "$vault_count"
  if [ -f "$SCRIPT_DIR/.env" ]; then
    _llm_p=$(grep -E '^[[:space:]]*DRAFT_LLM_PROVIDER[[:space:]]*=' "$SCRIPT_DIR/.env" 2>/dev/null | sed -E "s/^[^=]*=[[:space:]]*['\"]?//;s/['\"]?[[:space:]]*$//" | head -1)
    _llm_m=$(grep -E '^[[:space:]]*OLLAMA_MODEL[[:space:]]*=' "$SCRIPT_DIR/.env" 2>/dev/null | sed -E "s/^[^=]*=[[:space:]]*['\"]?//;s/['\"]?[[:space:]]*$//" | head -1)
    [ -z "$_llm_m" ] && _llm_m=$(grep -E '^[[:space:]]*DRAFT_LLM_MODEL[[:space:]]*=' "$SCRIPT_DIR/.env" 2>/dev/null | sed -E "s/^[^=]*=[[:space:]]*['\"]?//;s/['\"]?[[:space:]]*$//" | head -1)
    if [ -n "$_llm_p" ] || [ -n "$_llm_m" ]; then
      printf "  ${D}LLM: %s${N}\n" "${_llm_p:-ollama} / ${_llm_m:-?}"
    else
      printf "  ${D}LLM: not configured${N}\n"
    fi
    unset _llm_p _llm_m
  else
    printf "  ${D}LLM: not configured${N}\n"
  fi
  if [ -f "$SCRIPT_DIR/.env" ]; then
    _emb=$(grep -E '^[[:space:]]*DRAFT_EMBED_MODEL[[:space:]]*=' "$SCRIPT_DIR/.env" 2>/dev/null | sed -E "s/^[^=]*=[[:space:]]*['\"]?//;s/['\"]?[[:space:]]*$//" | head -1)
    _cross=$(grep -E '^[[:space:]]*DRAFT_CROSS_ENCODER_MODEL[[:space:]]*=' "$SCRIPT_DIR/.env" 2>/dev/null | sed -E "s/^[^=]*=[[:space:]]*['\"]*//;s/['\"]?[[:space:]]*$//" | head -1)
    [ -n "$_emb" ] && printf "  ${D}Embed: %s${N}\n" "$_emb"
    [ -n "$_cross" ] && printf "  ${D}Cross-encoder: %s${N}\n" "$_cross"
    unset _emb _cross
  fi
  if [ -d "$DRAFT_HOME/.vector_store" ] && [ -n "$(find "$DRAFT_HOME/.vector_store" -type f 2>/dev/null | head -1)" ]; then
    _rag_model=$(cd "$SCRIPT_DIR" && "$PYTHON" -c "
import sys
sys.path.insert(0, '.')
try:
    import chromadb
    from chromadb.config import Settings
    from lib.paths import get_vector_store_root
    from lib.ingest import COLLECTION_NAME
    client = chromadb.PersistentClient(path=str(get_vector_store_root()), settings=Settings(anonymized_telemetry=False))
    col = client.get_collection(COLLECTION_NAME)
    meta = getattr(col, 'metadata', None) or {}
    # Prefer embed model name (algorithm); fall back to profile for old index
    print(meta.get('embed_model') or meta.get('profile', '?'))
except Exception:
    print('')
" 2>/dev/null) || _rag_model=""
    _rag_model="${_rag_model:-?}"
    printf "  ${D}RAG index: %s${N}\n" "$_rag_model"
  else
    printf "  ${D}RAG index: not built${N}\n"
  fi
  echo ""
}

# Detect new vs existing install. Do not use sources.yaml — initial file is copied from
# sources.example.yaml and always contains vault + draft with source:. Use on-disk content only.
# New = no files in .doc_sources and no files in vault. Existing = at least one file in either.
# Return 0 = existing install, 1 = new install. Sets DRAFT_INSTALL_STATE for use by later steps.
is_existing_install() {
  DRAFT_INSTALL_STATE="new"
  # Existing if .doc_sources has any subdir with at least one file
  if [ -d "$DRAFT_HOME/.doc_sources" ]; then
    if [ -n "$(find "$DRAFT_HOME/.doc_sources" -mindepth 2 -type f 2>/dev/null | head -1)" ]; then
      DRAFT_INSTALL_STATE="existing"
      return 0
    fi
  fi
  # Existing if vault has at least one file
  if [ -d "$DRAFT_HOME/vault" ]; then
    if [ -n "$(find "$DRAFT_HOME/vault" -type f 2>/dev/null | head -1)" ]; then
      DRAFT_INSTALL_STATE="existing"
      return 0
    fi
  fi
  return 1
}

# --- Managed sources: offer to add new sources ---
ensure_sources_yaml
is_existing_install || true
export DRAFT_INSTALL_STATE
# Verify sources.yaml before reading it (mandatory: fail if invalid)
if ! (cd "$SCRIPT_DIR" && "$PYTHON" scripts/verify_sources.py -r "$SCRIPT_DIR" -q 2>/dev/null); then
  printf "${R}sources.yaml is invalid. Fix errors and re-run setup. Run: %s scripts/verify_sources.py -r %s${N}\n" "$PYTHON" "$SCRIPT_DIR" >&2
  (cd "$SCRIPT_DIR" && "$PYTHON" scripts/verify_sources.py -r "$SCRIPT_DIR" 2>&1) || true
  exit 1
fi
# Make sources.yaml follow actual content (vault + .doc_sources). Content on disk is source of truth.
printf "${D}Syncing sources.yaml from on-disk content...${N}\n"
sync_sources_yaml_from_content
# Sync doc sources from sources.yaml to .doc_sources (no AI index build).
printf "${D}Syncing doc sources from sources.yaml...${N}\n"
(cd "$SCRIPT_DIR" && "$PYTHON" scripts/pull.py -q 2>/dev/null) || true
echo ""

check_venv() { [[ -d "$SCRIPT_DIR/.venv" ]]; }

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

# Default embedding and cross-encoder models (Hugging Face, run locally)
DEFAULT_EMBED_MODEL="sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_CROSS_ENCODER_MODEL="cross-encoder/ms-marco-MiniLM-L-6-v2"

# Read a key from .env (strip quotes). Usage: env_val "DRAFT_EMBED_MODEL" "default"
env_val() {
  local key="$1"
  local default="${2:-}"
  local line
  line="$(grep -E "^${key}=" "$SCRIPT_DIR/.env" 2>/dev/null | head -1)" || true
  if [ -n "$line" ]; then
    line="${line#*=}"
    line="$(printf '%s' "$line" | sed "s/^['\"]//;s/['\"]$//")"
    printf '%s' "$line"
  else
    printf '%s' "$default"
  fi
}

# One-liner feature for known embed models
embed_model_feature() {
  case "$1" in
    sentence-transformers/all-MiniLM-L6-v2)
      printf "Fast, small, good for most use cases"
      ;;
    BAAI/bge-small-en-v1.5)
      printf "Small, strong quality for English"
      ;;
    nomic-ai/nomic-embed-text-v1.5)
      printf "Higher quality, longer context"
      ;;
    mixedbread-ai/mxbai-embed-large-v1)
      printf "Strong MTEB performance, 1024 dims"
      ;;
    *)
      if printf '%s' "$1" | grep -q '/'; then
        printf "Hugging Face model"
      else
        printf "Ollama model"
      fi
      ;;
  esac
}

# Option 2: Setup embedding model. Show current, suggest 3 HF models, list local Ollama, allow custom HF input.
do_config_embed_flow() {
  local current_encoder
  current_encoder="$(env_val "DRAFT_CROSS_ENCODER_MODEL" "$DEFAULT_CROSS_ENCODER_MODEL")"
  [ -z "$current_encoder" ] && current_encoder="$DEFAULT_CROSS_ENCODER_MODEL"

  # Save current embed model from .env before any change (for compare-after-write)
  local prev_embed
  prev_embed="$(env_val "DRAFT_EMBED_MODEL" "$DEFAULT_EMBED_MODEL")"
  [ -z "$prev_embed" ] && prev_embed="$DEFAULT_EMBED_MODEL"

  printf "\n${D}--- Setup embedding model ---${N}\n"
  printf "  ${G}[Current]${N} %s — %s\n" "$prev_embed" "$(embed_model_feature "$prev_embed")"
  echo ""
  printf "  N) No change (use current model) [default]\n"
  printf "  ${D}Suggested Hugging Face models: ${Y}[all HF models will be downloaded and run locally for privacy]${N}\n"
  printf "  ${D}16GB laptop (no GPU): prefer 1 or nomic-ai/nomic-embed-text-v1.5.${N}\n"
  printf "  1) sentence-transformers/all-MiniLM-L6-v2 — %s\n" "$(embed_model_feature "sentence-transformers/all-MiniLM-L6-v2")"
  printf "  2) BAAI/bge-small-en-v1.5 — %s\n" "$(embed_model_feature "BAAI/bge-small-en-v1.5")"
  printf "  3) mixedbread-ai/mxbai-embed-large-v1 — %s\n" "$(embed_model_feature "mixedbread-ai/mxbai-embed-large-v1")"
  echo ""
  OLLAMA_EMBED_AVAILABLE=()
  if command -v ollama >/dev/null 2>&1; then
    while IFS= read -r name; do
      [ -z "$name" ] && continue
      name_lower="$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')"
      if [[ "$name_lower" == *embed* ]] || [[ "$name_lower" == *embedding* ]]; then
        OLLAMA_EMBED_AVAILABLE+=("$name")
      fi
    done < <(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}')
  fi
  if [ ${#OLLAMA_EMBED_AVAILABLE[@]} -gt 0 ]; then
    printf "  ${D}Local Ollama models:${N}\n"
    local i=4
    for m in "${OLLAMA_EMBED_AVAILABLE[@]}"; do
      printf "  %s) %s (Ollama) — %s\n" "$i" "$m" "$(embed_model_feature "$m")"
      i=$((i + 1))
    done
    echo ""
  fi
  printf "  Enter N (default), 1, 2, 3, a number for Ollama, or type a Hugging Face model (e.g. org/model):\n"
  local choice
  read -r -p "Choice [N]: " choice
  choice="$(printf '%s' "$choice" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  local embed_model=""
  local embed_provider=""
  if [ -z "$choice" ] || [ "$(printf '%s' "$choice" | tr '[:upper:]' '[:lower:]')" = "n" ]; then
    printf "  ${D}No change. Keeping current model.${N}\n"
    printf "  ${D}First run may download the model from Hugging Face if not cached.${N}\n"
    echo ""
    return
  elif [ "$choice" = "1" ]; then
    embed_model="sentence-transformers/all-MiniLM-L6-v2"
  elif [ "$choice" = "2" ]; then
    embed_model="BAAI/bge-small-en-v1.5"
  elif [ "$choice" = "3" ]; then
    embed_model="mixedbread-ai/mxbai-embed-large-v1"
  elif printf '%s' "$choice" | grep -q '/'; then
    embed_model="$choice"
  else
    local idx=$((choice - 4))
    if [ "$idx" -ge 0 ] 2>/dev/null && [ "$idx" -lt ${#OLLAMA_EMBED_AVAILABLE[@]} ]; then
      embed_model="${OLLAMA_EMBED_AVAILABLE[$idx]}"
      embed_provider="ollama"
    else
      printf "  ${D}Invalid choice. Keeping current model.${N}\n"
      embed_model="$prev_embed"
    fi
  fi
  if [ -z "$embed_model" ]; then
    embed_model="$prev_embed"
  fi
  if [ -n "$embed_provider" ]; then
    (cd "$SCRIPT_DIR" && "$PYTHON" scripts/setup_embed_config.py "$embed_model" "$current_encoder" --provider "$embed_provider")
  else
    (cd "$SCRIPT_DIR" && "$PYTHON" scripts/setup_embed_config.py "$embed_model" "$current_encoder")
  fi
  printf "  ${G}✓${N} Embed model saved to .env.\n"
  if [ "$embed_model" != "$prev_embed" ]; then
    printf "  ${Y}You *must* rebuild the index with the new model in step 5 (Build RAG/index).${N}\n"
  fi
  printf "  ${D}First run may download the model from Hugging Face if not cached.${N}\n"
  echo ""
}

# Option 3: Setup encoder model. Default cross-encoder; user can type a different one.
do_config_encoder_flow() {
  local current_embed
  current_embed="$(env_val "DRAFT_EMBED_MODEL" "$DEFAULT_EMBED_MODEL")"
  [ -z "$current_embed" ] && current_embed="$DEFAULT_EMBED_MODEL"
  local current_provider
  current_provider="$(env_val "DRAFT_EMBED_PROVIDER" "")"

  printf "\n${D}--- Setup encoder (cross-encoder) model ---${N}\n"
  printf "  Default: %s\n" "$DEFAULT_CROSS_ENCODER_MODEL"
  printf "  ${D}16GB laptop: default (BGE-v2-m3) is fine.${N}\n"
  echo ""
  local input_encoder
  read -r -p "Encoder model (Enter for default): " input_encoder
  input_encoder="$(printf '%s' "$input_encoder" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  local cross_encoder_model="$DEFAULT_CROSS_ENCODER_MODEL"
  [ -n "$input_encoder" ] && cross_encoder_model="$input_encoder"
  if [ -n "$current_provider" ]; then
    (cd "$SCRIPT_DIR" && "$PYTHON" scripts/setup_embed_config.py "$current_embed" "$cross_encoder_model" --provider "$current_provider")
  else
    (cd "$SCRIPT_DIR" && "$PYTHON" scripts/setup_embed_config.py "$current_embed" "$cross_encoder_model")
  fi
  printf "  ${G}✓${N} Encoder model saved to .env. Ask and reindex use this encoder.\n"
  printf "  ${D}First run may download the model from Hugging Face if not cached.${N}\n"
  echo ""
}

# --- Action flows (used by both new-install wizard and existing-install menu) ---
do_add_sources_flow() {
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
      printf "  ${G}✓${N} Repo is reachable. Pull will clone/pull via git and sync .md files.\n"
      echo ""
      read -r -p "Add this GitHub source? (y/N): " yn
      yn="${yn:-n}"
      case "$yn" in
        [yY]|[yY][eE][sS])
          (cd "$SCRIPT_DIR" && "$PYTHON" scripts/pull.py -a "$src_path")
          printf "  ${G}✓${N} Added.\n"
          ;;
      esac
      echo ""
      continue
    fi
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
    read -r -p "Add this source? (y/N): " yn
    yn="${yn:-n}"
    case "$yn" in
      [yY]|[yY][eE][sS])
        (cd "$SCRIPT_DIR" && "$PYTHON" scripts/pull.py -a "$add_arg")
        printf "  ${G}✓${N} Added.\n"
        ;;
    esac
    echo ""
  done
  echo ""
}

do_config_llm_flow() {
  if [ "$DRAFT_CONFIG_LLM" = "Y" ]; then
    config_llm=y
  else
    read -r -p "Configure LLM for AI assistant? This will need an API key or local model. (y/N): " config_llm
    config_llm="${config_llm:-n}"
  fi
  case "$config_llm" in
    [yY]|[yY][eE][sS])
      echo ""
      env_file="$SCRIPT_DIR/.env"
      llm_start=10
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
          if [ -z "$api_key" ]; then printf "${D}Skipped.${N}\n"; break; fi
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
          if [ -z "$api_key" ]; then printf "${D}Skipped.${N}\n"; break; fi
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
          if [ -z "$api_key" ]; then printf "${D}Skipped.${N}\n"; break; fi
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
          if [ -z "$other_model" ]; then printf "${D}Skipped.${N}\n"; break; fi
          (cd "$SCRIPT_DIR" && "$PYTHON" scripts/setup_env_writer.py --mode ollama --model "$other_model")
          printf "  ${G}✓${N} Set .env: custom model %s (Ollama).\n" "$other_model"
          break
        else
          printf "  ${R}Enter a number 1-%s.${N}\n" "$max_choice"
        fi
      done
      echo ""
      printf "  ${D}If you run Draft in Docker, restart the container (option 8) to pick up the new LLM.${N}\n"
      ;;
    *)
      echo "Skipping LLM configuration."
      ;;
  esac
}

do_build_rag_flow() {
  if ! (cd "$SCRIPT_DIR" && "$PYTHON" scripts/check_llm_ready.py 2>/dev/null); then
    printf "${D}LLM not configured; skip RAG build. Configure LLM first.${N}\n"
    return
  fi
  if [ "$DRAFT_BUILD_RAG" = "Y" ]; then
    build_rag=1
    rag_profile="quick"
  else
    while true; do
      read -r -p "Build RAG/index now? You can also do this later from the UI. (y/N): " build_rag
      build_rag="$(printf '%s' "${build_rag:-n}" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
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
    fi
  fi
  if [ "$build_rag" = "1" ]; then
    # Avoid duplicate rebuild: if index already built with current model, ask to confirm
    _baseline=""
    if [ -d "$DRAFT_HOME/.vector_store" ] && [ -n "$(find "$DRAFT_HOME/.vector_store" -type f 2>/dev/null | head -1)" ]; then
      _baseline=$(cd "$SCRIPT_DIR" && "$PYTHON" -c "
import sys
sys.path.insert(0, '.')
try:
    import chromadb
    from chromadb.config import Settings
    from lib.paths import get_vector_store_root
    from lib.ingest import COLLECTION_NAME
    client = chromadb.PersistentClient(path=str(get_vector_store_root()), settings=Settings(anonymized_telemetry=False))
    col = client.get_collection(COLLECTION_NAME)
    meta = getattr(col, 'metadata', None) or {}
    print(meta.get('embed_model') or meta.get('profile', '') or '')
except Exception:
    print('')
" 2>/dev/null) || true
    fi
    _current="$(env_val "DRAFT_EMBED_MODEL" "$DEFAULT_EMBED_MODEL")"
    [ -z "$_current" ] && _current="$DEFAULT_EMBED_MODEL"
    if [ -n "$_baseline" ] && [ "$_current" = "$_baseline" ]; then
      read -r -p "The current index was built with the current model. If a rebuild is indeed needed? (y/N): " _confirm_rebuild
      _confirm_rebuild="$(printf '%s' "${_confirm_rebuild:-n}" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      if [ "$_confirm_rebuild" != "y" ] && [ "$_confirm_rebuild" != "yes" ]; then
        build_rag=0
        printf "  ${D}Skipping rebuild.${N}\n"
      fi
      unset _confirm_rebuild
    fi
    unset _baseline _current
  fi
  if [ "$build_rag" = "1" ]; then
    printf "${D}Build RAG/vector index ...${N}\n"
    "$SCRIPT_DIR/.venv/bin/pip" install -q -r "$REQUIREMENTS_FILE" 2>/dev/null || true
    if (cd "$SCRIPT_DIR" && "$PYTHON" scripts/index_for_ai.py --profile "$rag_profile" -v); then
      printf "${G}done.${N}\n"
      _emb="$(env_val "DRAFT_EMBED_MODEL" "$DEFAULT_EMBED_MODEL")"
      [ -z "$_emb" ] && _emb="$DEFAULT_EMBED_MODEL"
      echo ""
      read -r -p "The index is rebuilt with the new embed model ${_emb}. Would you like to run a test? (Y/n): " run_test
      run_test="$(printf '%s' "${run_test:-y}" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      if [ "$run_test" = "y" ] || [ "$run_test" = "yes" ] || [ -z "$run_test" ]; then
        printf "${D}Running ask.py test ...${N}\n"
        (cd "$SCRIPT_DIR" && "$PYTHON" scripts/ask.py -q "Explain the ingestion process for Draft's RAG system and how it handles different embedding providers like Ollama and Hugging Face." --debug --show-prompt) || true
      fi
      unset _emb
    else
      printf "${R}failed (Ask index not built).${N}\n" >&2
    fi
  fi
}

do_start_ui_flow() {
  if [ "$DRAFT_START_UI" = "Y" ]; then
    start_ui=y
  else
    read -r -p "Start or restart the Draft UI? (Y/n): " start_ui
    start_ui="${start_ui:-y}"
  fi
  case "$start_ui" in
    [yY]|[yY][eE][sS])
      _UI_LOG="${DRAFT_HOME}/.draft-ui.log"
      nohup "$PYTHON" "$SCRIPT_DIR/scripts/serve.py" >> "$_UI_LOG" 2>&1 &
      _UI_PID=$!
      ( sleep 2; case "$OS" in Darwin) open "http://localhost:8058" ;; *) xdg-open "http://localhost:8058" 2>/dev/null || true ;; esac ) &
      printf "  ${G}Draft UI started in background${N} (PID %s). Log: %s\n" "$_UI_PID" "$_UI_LOG"
      printf "  ${D}Stop with: kill %s${N}\n" "$_UI_PID"
      ;;
    *)
      printf "${D}Skipped.${N}\n"
      printf "You can start Draft later by running this setup.sh again or by running:\n"
      printf "  source .venv/bin/activate\n"
      printf "  python scripts/serve.py\n"
      echo ""
      ;;
  esac
}

# Read a key from .env (stripped). Usage: _env_val KEY .env
_env_val() {
  local key="$1" file="${2:-$SCRIPT_DIR/.env}"
  [ ! -f "$file" ] && return 0
  grep -E "^[[:space:]]*${key}[[:space:]]*=" "$file" 2>/dev/null | sed -E "s/^[^=]*=[[:space:]]*['\"]?//;s/['\"]?[[:space:]]*$//" | head -1
}

# Docker-specific env: OLLAMA_HOST so container can reach host Ollama. Only when using local Ollama.
ensure_env_docker() {
  local env_docker="$SCRIPT_DIR/.env.docker"
  if [ ! -f "$env_docker" ] || ! grep -q "OLLAMA_HOST" "$env_docker" 2>/dev/null; then
    printf "# Docker-only overrides (used with: docker run --env-file .env --env-file .env.docker)\n" > "$env_docker"
    printf "# OLLAMA_HOST lets the container reach Ollama on the host (Docker Desktop: host.docker.internal)\n" >> "$env_docker"
    printf "OLLAMA_HOST=http://host.docker.internal:11434\n" >> "$env_docker"
    printf "  ${G}Created %s${N}\n" "$env_docker"
  fi
}

do_docker_flow() {
  printf "\n${D}--- Run Draft in a Docker container ---${N}\n"
  if ! command -v docker >/dev/null 2>&1; then
    printf "  ${R}Docker not found. Install Docker Desktop (or docker-engine) and try again.${N}\n"
    return 1
  fi
  if ! docker info >/dev/null 2>&1; then
    printf "  ${R}Docker daemon is not running.${N}\n"
    case "$(uname -s)" in
      Darwin) printf "  Start Docker Desktop from Applications or the menu bar, then try again.${N}\n" ;;
      *)      printf "  Start the docker service (e.g. sudo systemctl start docker), then try again.${N}\n" ;;
    esac
    return 1
  fi
  if [ ! -f "$SCRIPT_DIR/.env" ] && [ -f "$SCRIPT_DIR/.env.example" ]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    printf "  ${G}Created .env from .env.example. Edit .env if you need to set LLM/embed config.${N}\n"
  fi

  # Detect LLM config so Docker run aligns with local settings
  local provider ollama_model anth_key gemini_key openai_key use_ollama use_cloud
  provider="$(_env_val DRAFT_LLM_PROVIDER)"
  provider="$(printf '%s' "$provider" | tr '[:upper:]' '[:lower:]')"
  ollama_model="$(_env_val OLLAMA_MODEL)"
  [ -z "$ollama_model" ] && ollama_model="$(_env_val DRAFT_LLM_MODEL)"
  anth_key="$(_env_val ANTHROPIC_API_KEY)"
  gemini_key="$(_env_val GEMINI_API_KEY)"
  [ -z "$gemini_key" ] && gemini_key="$(_env_val GOOGLE_API_KEY)"
  openai_key="$(_env_val OPENAI_API_KEY)"

  use_ollama=0
  use_cloud=0
  if [ "$provider" = "ollama" ] || { [ -z "$provider" ] && [ -n "$ollama_model" ]; }; then
    use_ollama=1
  fi
  if [ "$provider" = "claude" ] && [ -n "$anth_key" ]; then
    use_cloud=1
  fi
  if [ "$provider" = "gemini" ] && [ -n "$gemini_key" ]; then
    use_cloud=1
  fi
  if [ "$provider" = "openai" ] && [ -n "$openai_key" ]; then
    use_cloud=1
  fi

  if [ "$use_ollama" -eq 1 ]; then
    ensure_env_docker
    printf "  ${G}Local LLM (Ollama) detected.${N} Container will use OLLAMA_HOST to reach host Ollama.\n"
  elif [ "$use_cloud" -eq 1 ]; then
    printf "  ${G}Cloud LLM configured.${N} Container will use your API keys from .env.\n"
  else
    printf "  ${D}No LLM configured.${N} Ask (AI) / semantic search will not work in the container.\n"
    printf "  Configure LLM in option 4 (Configure LLM), or run Docker to browse docs only.\n"
    read -r -p "Run anyway (browse docs only)? (y/N): " run_anyway
    run_anyway="$(printf '%s' "${run_anyway:-n}" | tr '[:upper:]' '[:lower:]')"
    case "$run_anyway" in
      [yY]|[yY][eE][sS]) ;;
      *)
        printf "  ${D}Exiting. Choose option 4 to configure LLM, then try Docker again.${N}\n"
        return 0
        ;;
    esac
  fi

  if ! docker image inspect draft-ui >/dev/null 2>&1; then
    read -r -p "Build the draft-ui image now? (Y/n): " build_choice
    build_choice="${build_choice:-y}"
    case "$build_choice" in
      [yY]|[yY][eE][sS])
        printf "  ${D}Building image...${N}\n"
        (cd "$SCRIPT_DIR" && docker build -t draft-ui .) || return 1
        printf "  ${G}Image draft-ui built.${N}\n"
        ;;
      *)
        printf "  ${D}Build later with: docker build -t draft-ui .${N}\n"
        return 0
        ;;
    esac
  fi

  # If a draft-ui container is already running, stop it so we start fresh with current .env
  _running=$(docker ps -q --filter "ancestor=draft-ui" 2>/dev/null)
  if [ -n "$_running" ]; then
    printf "  ${D}Stopping existing draft-ui container...${N}\n"
    docker stop $_running 2>/dev/null || true
    sleep 2
  fi
  unset _running

  printf "  Starting container (port 8058, data from %s)...\n" "$DRAFT_HOME"
  printf "  ${D}Mounting .env. HF cache lives under DRAFT_HOME/.cache/huggingface (no separate volume).${N}\n"
  _env_abs=""
  if [ -f "$SCRIPT_DIR/.env" ]; then
    _env_abs="$(cd "$SCRIPT_DIR" 2>/dev/null && pwd)/.env"
  fi
  _vol_env=""
  [ -n "$_env_abs" ] && _vol_env="-v ${_env_abs}:/app/.env:ro"
  if [ "$use_ollama" -eq 1 ]; then
    printf "  ${D}Using --env-file .env and .env.docker (OLLAMA_HOST for host Ollama).${N}\n"
    docker run -p 8058:8058 \
      -v "${DRAFT_HOME}:/.draft" \
      $_vol_env \
      -e DRAFT_HOME=/.draft \
      --env-file "$SCRIPT_DIR/.env" \
      --env-file "$SCRIPT_DIR/.env.docker" \
      draft-ui
  else
    printf "  ${D}Using --env-file .env.${N}\n"
    docker run -p 8058:8058 \
      -v "${DRAFT_HOME}:/.draft" \
      $_vol_env \
      -e DRAFT_HOME=/.draft \
      --env-file "$SCRIPT_DIR/.env" \
      draft-ui
  fi
  # Note: container runs in foreground; when user Ctrl+C, container stops. For daemon: add -d.
}

# --- Main flow: menu (single entrance for new and existing installs) ---
printf "${D}--- Environment check ---${N}\n"
printf "  %b\n" "$(check_venv && echo "${G}✓${N} .venv exists" || echo "${R}✗${N} .venv missing")"
echo ""

while true; do
  show_current_state
  printf "${D}Consistency check:${N}\n"
  check_sources_consistency
  show_actions
  echo ""
  printf "${D}Default embed and encoder are set. Change them via options 2 and 3.${N}\n"
  printf "${D}For semantic search via LLM: option 4 (Configure LLM) and option 5 (Build RAG index).${N}\n"
  printf "${D}To configure manually, edit .env: DRAFT_EMBED_MODEL, DRAFT_CROSS_ENCODER_MODEL, DRAFT_LLM_PROVIDER, OLLAMA_MODEL, etc.${N}\n"
  echo ""
  printf "What should the setup do next?\n"
  printf "  1) Add doc sources\n"
  printf "  2) Setup embedding model\n"
  printf "  3) Setup encoder model\n"
  printf "  4) Configure LLM\n"
  printf "  5) Build RAG/index (chunking and embeddings)\n"
  printf "  6) Test RAG + LLM\n"
  printf "  7) Start/restart the Draft UI in the local host (default)\n"
  printf "  8) Run Draft in a Docker container\n"
  printf "  9) Done/Exit the setup\n"
  read -r -p "Choice (1-9) [7]: " menu_choice
  menu_choice="${menu_choice:-7}"
  case "$menu_choice" in
    1) DRAFT_ADD_SOURCES=Y do_add_sources_flow ;;
    2) do_config_embed_flow ;;
    3) do_config_encoder_flow ;;
    4) DRAFT_CONFIG_LLM=Y do_config_llm_flow ;;
    5) DRAFT_BUILD_RAG=Y do_build_rag_flow ;;
    6) printf "${D}Running RAG + LLM test ...${N}\n"; (cd "$SCRIPT_DIR" && "$PYTHON" scripts/ask.py -q "Explain the ingestion process for Draft's RAG system and how it handles different embedding providers like Ollama and Hugging Face." --debug --show-prompt) || true ;;
    7) DRAFT_START_UI=Y do_start_ui_flow; exit 0 ;;
    8) do_docker_flow; exit 0 ;;
    9) printf "${D}Done.${N}\n"; exit 0 ;;
    *) printf "${D}Invalid.${N}\n" ;;
  esac
  echo ""
done
