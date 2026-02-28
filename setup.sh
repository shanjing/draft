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
  if [ -d "$SCRIPT_DIR/.vector_store" ] && [ -n "$(find "$SCRIPT_DIR/.vector_store" -type f 2>/dev/null | head -1)" ]; then
    _rag_model=$(cd "$SCRIPT_DIR" && "$PYTHON" -c "
import sys
sys.path.insert(0, '.')
try:
    import chromadb
    from chromadb.config import Settings
    from lib.ingest import VECTOR_DIR, COLLECTION_NAME
    client = chromadb.PersistentClient(path=VECTOR_DIR, settings=Settings(anonymized_telemetry=False))
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

# Map Ollama embedding model name -> Hugging Face equivalent (for sentence-transformers).
# Models without a mapping use the Ollama name (requires Ollama embedding support in lib).
ollama_embed_to_hf() {
  local name="$1"
  case "$name" in
    nomic-embed-text*) echo "nomic-ai/nomic-embed-text-v1.5" ;;
    qwen3-embedding:8b*) echo "Qwen/Qwen3-Embedding-8B" ;;
    qwen3-embedding:0.6b*) echo "Qwen/Qwen3-Embedding-0.6B" ;;
    qwen3-embedding*) echo "Qwen/Qwen3-Embedding-8B" ;;
    *) echo "$name" ;;
  esac
}

# Qwen3 pairs: embedding + reranker. Gold = 8b embed + 0.6B reranker (best balance).
OLLAMA_QWEN3_8B_EMBED="qwen3-embedding:8b"
OLLAMA_QWEN3_8B_RERANKER="dengcao/Qwen3-Reranker-8B:Q3_K_M"
OLLAMA_QWEN3_06B_EMBED="qwen3-embedding:0.6b"
OLLAMA_QWEN3_06B_RERANKER="dengcao/Qwen3-Reranker-0.6B:Q8_0"
# Hugging Face model names for embed + cross-encoder (sentence-transformers)
HF_QWEN3_8B_EMBED="Qwen/Qwen3-Embedding-8B"
HF_QWEN3_8B_RERANKER="dengcao/Qwen3-Reranker-8B"
HF_QWEN3_06B_EMBED="Qwen/Qwen3-Embedding-0.6B"
HF_QWEN3_06B_RERANKER="dengcao/Qwen3-Reranker-0.6B"

do_config_embed_flow() {
  local embed_model="$DEFAULT_EMBED_MODEL"
  local cross_encoder_model="$DEFAULT_CROSS_ENCODER_MODEL"
  local has_local=0
  local use_cloud_embed=0
  local use_ollama_embed=0
  local mem_gb=0
  local cpu_count=0
  local skip_to_summary=0
  local qwen3_all_present=0

  printf "\n${D}--- Configure embedding and cross-encoder models ---${N}\n"
  printf "  Default: embed=%s, cross-encoder=%s\n" "$DEFAULT_EMBED_MODEL" "$DEFAULT_CROSS_ENCODER_MODEL"
  echo ""

  # Step 1: If Ollama found, suggest Qwen3 pairs and offer to download (unless already present)
  if command -v ollama >/dev/null 2>&1; then
    OLLAMA_NAMES=""
    while IFS= read -r n; do [ -n "$n" ] && OLLAMA_NAMES="${OLLAMA_NAMES}${OLLAMA_NAMES:+ }$n"; done < <(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}')
    qwen3_all_present=1
    for want in "$OLLAMA_QWEN3_8B_EMBED" "$OLLAMA_QWEN3_8B_RERANKER" "$OLLAMA_QWEN3_06B_EMBED" "$OLLAMA_QWEN3_06B_RERANKER"; do
      if [[ " $OLLAMA_NAMES " != *" $want "* ]]; then
        qwen3_all_present=0
        break
      fi
    done
    if [ "$qwen3_all_present" = "1" ]; then
      printf "  ${G}Qwen3 pairs already available (Ollama).${N}\n"
    else
      printf "  ${G}Suggested Qwen3 pairs (embedding + reranker):${N}\n"
      printf "    - Gold : %s + %s (best balance: deep memory, fast verification, takes more time to build the index)${N}\n" "$OLLAMA_QWEN3_8B_EMBED" "$OLLAMA_QWEN3_06B_RERANKER"
      printf "    - 8B+8B:  %s + %s${N}\n" "$OLLAMA_QWEN3_8B_EMBED" "$OLLAMA_QWEN3_8B_RERANKER"
      printf "    - 0.6B+0.6B: %s + %s${N}\n" "$OLLAMA_QWEN3_06B_EMBED" "$OLLAMA_QWEN3_06B_RERANKER"
      printf "    **Note**: for most Macbooks, Mac Mini and PCs, use the default model.${N}"
      echo ""
      read -r -p "Download these pairs from Ollama? (y/N): " download_choice
      download_choice="$(printf '%s' "${download_choice:-n}" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      if [ "$download_choice" = "y" ] || [ "$download_choice" = "yes" ]; then
        printf "  ${D}Pulling models...${N}\n"
        ollama pull "$OLLAMA_QWEN3_8B_EMBED" || true
        ollama pull "$OLLAMA_QWEN3_8B_RERANKER" || true
        ollama pull "$OLLAMA_QWEN3_06B_EMBED" || true
        ollama pull "$OLLAMA_QWEN3_06B_RERANKER" || true
        printf "  ${G}Done.${N}\n"
      else
        skip_to_summary=1
        printf "  ${D}Using default models.${N}\n"
      fi
    fi
  fi

  # If user chose N, skip to summary
  if [ "$skip_to_summary" = "1" ]; then
    (cd "$SCRIPT_DIR" && "$PYTHON" scripts/setup_embed_config.py "$embed_model" "$cross_encoder_model")
    printf "  ${G}✓${N} Config saved to .env. Rebuild RAG index to apply.\n"
    echo ""
    return
  fi

  # Step 2: Dynamically detect embedding models from ollama list (names containing "embed" or "embedding")
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
    has_local=1
    # Step 3: Check hardware and suggest
    case "$OS" in
      Darwin)
        mem_gb=$(($(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1024 / 1024 / 1024))
        cpu_count=$(sysctl -n hw.ncpu 2>/dev/null || echo 0)
        ;;
      Linux)
        mem_gb=$(($(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}') / 1024 / 1024))
        cpu_count=$(nproc 2>/dev/null || echo 0)
        ;;
      *) mem_gb=0; cpu_count=0 ;;
    esac

    printf "  ${G}Local Qwen3 models detected (Ollama):${N}\n"
    if [ "$qwen3_all_present" = "1" ]; then
      printf "    - %s -> %s (embed)${N}\n" "$OLLAMA_QWEN3_8B_EMBED" "$HF_QWEN3_8B_EMBED"
      printf "    - %s -> %s (embed)${N}\n" "$OLLAMA_QWEN3_06B_EMBED" "$HF_QWEN3_06B_EMBED"
      printf "    - %s (reranker)${N}\n" "$OLLAMA_QWEN3_8B_RERANKER"
      printf "    - %s (reranker)${N}\n" "$OLLAMA_QWEN3_06B_RERANKER"
    else
      for m in "${OLLAMA_EMBED_AVAILABLE[@]}"; do
        suggested="$(ollama_embed_to_hf "$m")"
        if [ "$suggested" = "$m" ]; then
          printf "    - %s (Ollama; lib support may be needed)${N}\n" "$m"
        else
          printf "    - %s -> %s (HF)${N}\n" "$m" "$suggested"
        fi
      done
    fi
    if [ "$mem_gb" -ge 8 ]; then
      printf "  ${D}Hardware: %s GB RAM, %s CPU(s). Local models recommended for better accuracy.${N}\n" "$mem_gb" "$cpu_count"
    else
      printf "  ${D}Hardware: %s GB RAM. Default models are lighter; local models may use more memory.${N}\n" "$mem_gb"
    fi
    printf "  ${D}Default models work well. Local models can offer more accurate results but may takes hours to build the vectorindexes.${N}\n"
    echo ""

    # Step 4: Ask default, Qwen3 pair (G/L/S), or first local
    if [ "$qwen3_all_present" = "1" ]; then
      printf "  ${D}G=Gold (8b embed + 0.6B reranker, recommended), L=(8B embed + 8B reranker, slow), S=(0.6B embed + 0.6B reranker fast)${N}\n"
      read -r -p "Use default (d), Gold (G), 8B+8B (L), or 0.6B+0.6B (S)? [d/G/L/S] (default d): " choice
      choice="$(printf '%s' "${choice:-d}" | tr '[:lower:]' '[:upper:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      case "$choice" in
        G)
          embed_model="$OLLAMA_QWEN3_8B_EMBED"
          cross_encoder_model="$OLLAMA_QWEN3_06B_RERANKER"
          use_ollama_embed=1
          printf "  ${G}Using Gold pair: embed=%s, reranker=%s (Ollama, no download)${N}\n" "$embed_model" "$cross_encoder_model"
          ;;
        L)
          embed_model="$OLLAMA_QWEN3_8B_EMBED"
          cross_encoder_model="$OLLAMA_QWEN3_8B_RERANKER"
          use_ollama_embed=1
          printf "  ${G}Using 8B+8B pair: embed=%s, reranker=%s (Ollama, no download)${N}\n" "$embed_model" "$cross_encoder_model"
          ;;
        S)
          embed_model="$OLLAMA_QWEN3_06B_EMBED"
          cross_encoder_model="$OLLAMA_QWEN3_06B_RERANKER"
          use_ollama_embed=1
          printf "  ${G}Using 0.6B+0.6B pair: embed=%s, reranker=%s (Ollama, no download)${N}\n" "$embed_model" "$cross_encoder_model"
          ;;
        *)
          printf "  ${D}Using default models.${N}\n"
          ;;
      esac
    else
      read -r -p "Use default models (d) or local Ollama models (l)? [d/l] (default d): " choice
      choice="$(printf '%s' "${choice:-d}" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      if [ "$choice" = "l" ] && [ ${#OLLAMA_EMBED_AVAILABLE[@]} -gt 0 ]; then
        first_ollama="${OLLAMA_EMBED_AVAILABLE[0]}"
        embed_model="$first_ollama"
        use_ollama_embed=1
        printf "  ${G}Using local embed: %s (Ollama, no download), cross-encoder stays %s${N}\n" "$embed_model" "$cross_encoder_model"
      else
        printf "  ${D}Using default models.${N}\n"
      fi
    fi
  else
    # Step 5: No local models
    printf "  ${D}No local embedding models found (Ollama). Default models are already set.${N}\n"
    read -r -p "Use cloud-based embedding models? (y/N): " use_cloud
    use_cloud="$(printf '%s' "${use_cloud:-n}" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    if [ "$use_cloud" = "y" ] || [ "$use_cloud" = "yes" ]; then
      printf "  ${D}Cloud embedding providers: OpenAI (text-embedding-3-small).${N}\n"
      read -r -p "Skip and use default? (Y/n): " skip_cloud
      skip_cloud="$(printf '%s' "${skip_cloud:-y}" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      if [ "$skip_cloud" != "n" ] && [ "$skip_cloud" != "no" ]; then
        printf "  ${D}Using default models.${N}\n"
      else
        read -r -p "Embedding model (e.g. text-embedding-3-small): " cloud_embed
        cloud_embed="$(printf '%s' "$cloud_embed" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        if [ -z "$cloud_embed" ]; then
          printf "  ${D}Skipped. Using default.${N}\n"
        else
          read -r -s -p "OpenAI API key: " api_key
          echo ""
          api_key="$(printf '%s' "$api_key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
          if [ -z "$api_key" ]; then
            printf "  ${D}Skipped. Using default.${N}\n"
          else
            printf "${D}Verifying...${N}\n"
            if verify_openai_key "$api_key"; then
              (cd "$SCRIPT_DIR" && "$PYTHON" scripts/setup_env_writer.py --mode openai --model "gpt-4o-mini" --api-key "$api_key" 2>/dev/null) || true
              embed_model="$cloud_embed"
              use_cloud_embed=1
              printf "  ${G}API key valid. Cloud embedding configured (requires RAG index rebuild).${N}\n"
            else
              printf "  ${R}Invalid key. Using default models.${N}\n"
            fi
          fi
        fi
      fi
    fi
  fi

  # Step 6: Summary and write config
  while true; do
    printf "\n  ${D}Summary:${N}\n"
    printf "    embed_model: %s%s\n" "$embed_model" "$([ "$use_ollama_embed" = "1" ] && printf ' (Ollama, no download)' || true)"
    printf "    cross_encoder_model: %s\n" "$cross_encoder_model"
    echo ""
    read -r -p "Press C to continue (default), M to modify: " confirm
    confirm="$(printf '%s' "${confirm:-c}" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    case "$confirm" in
      c)
        if [ "$use_cloud_embed" = "1" ]; then
          (cd "$SCRIPT_DIR" && "$PYTHON" scripts/setup_embed_config.py "$embed_model" "$cross_encoder_model" --provider openai)
        elif [ "$use_ollama_embed" = "1" ]; then
          (cd "$SCRIPT_DIR" && "$PYTHON" scripts/setup_embed_config.py "$embed_model" "$cross_encoder_model" --provider ollama)
        else
          (cd "$SCRIPT_DIR" && "$PYTHON" scripts/setup_embed_config.py "$embed_model" "$cross_encoder_model")
        fi
        printf "  ${G}✓${N} Config saved to .env. Rebuild RAG index to apply.\n"
        break
        ;;
      m)
        use_cloud_embed=0
        if [ "$has_local" = "1" ]; then
          if [ "$qwen3_all_present" = "1" ]; then
            read -r -p "Use default (d), Gold (G), 8B+8B (L), or 0.6B+0.6B (S)? [d/G/L/S]: " choice
            choice="$(printf '%s' "${choice:-d}" | tr '[:lower:]' '[:upper:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
            case "$choice" in
              G)
                embed_model="$OLLAMA_QWEN3_8B_EMBED"
                cross_encoder_model="$OLLAMA_QWEN3_06B_RERANKER"
                use_ollama_embed=1
                ;;
              L)
                embed_model="$OLLAMA_QWEN3_8B_EMBED"
                cross_encoder_model="$OLLAMA_QWEN3_8B_RERANKER"
                use_ollama_embed=1
                ;;
              S)
                embed_model="$OLLAMA_QWEN3_06B_EMBED"
                cross_encoder_model="$OLLAMA_QWEN3_06B_RERANKER"
                use_ollama_embed=1
                ;;
              *)
                embed_model="$DEFAULT_EMBED_MODEL"
                cross_encoder_model="$DEFAULT_CROSS_ENCODER_MODEL"
                use_ollama_embed=0
                ;;
            esac
          else
            read -r -p "Use default (d) or local (l)? [d]: " choice
            choice="${choice:-d}"
            if [ "$choice" = "l" ]; then
              first_ollama="${OLLAMA_EMBED_AVAILABLE[0]}"
              embed_model="$first_ollama"
              use_ollama_embed=1
            else
              embed_model="$DEFAULT_EMBED_MODEL"
              use_ollama_embed=0
            fi
          fi
        else
          embed_model="$DEFAULT_EMBED_MODEL"
          cross_encoder_model="$DEFAULT_CROSS_ENCODER_MODEL"
        fi
        ;;
      *) printf "  ${D}Invalid. Use C or M.${N}\n" ;;
    esac
  done
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
    printf "${D}Build RAG/vector index ...${N}\n"
    "$SCRIPT_DIR/.venv/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt" 2>/dev/null || true
    if (cd "$SCRIPT_DIR" && "$PYTHON" scripts/index_for_ai.py --profile "$rag_profile" -v); then
      printf "${G}done.${N}\n"
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

# --- Main flow: menu (single entrance for new and existing installs) ---
printf "${D}--- Environment check ---${N}\n"
printf "  %b\n" "$(check_venv && echo "${G}✓${N} .venv exists" || echo "${R}✗${N} .venv missing")"
echo ""

while true; do
  show_current_state
  printf "${D}Consistency check:${N}\n"
  check_sources_consistency
  echo ""
  printf "${D}Default models for embedding and cross-encoder are already set. You can change them via step 2 below.${N}\n"
  printf "${D}If this is your first time setting up Draft and you want semantic search via LLM, we recommend${N}\n"
  printf "${D}step 3 (Configure LLM) and step 4 (Build RAG index). Choosing different embedding models is optional.${N}\n"
  printf "${D}To configure manually, edit .env and set DRAFT_EMBED_MODEL, DRAFT_CROSS_ENCODER_MODEL, DRAFT_LLM_PROVIDER, OLLAMA_MODEL, etc.${N}\n"
  echo ""
  printf "What should the setup do next?\n"
  printf "  1) Add doc sources\n"
  printf "  2) Configure embedding/cross-encoder models\n"
  printf "  3) Configure LLM\n"
  printf "  4) Build RAG/index (chunking and embeddings)\n"
  printf "  5) Start or restart the Draft UI\n"
  printf "  6) Done/Exit the setup\n"
  read -r -p "Choice (1-6) [5]: " menu_choice
  menu_choice="${menu_choice:-5}"
  case "$menu_choice" in
    1) DRAFT_ADD_SOURCES=Y do_add_sources_flow ;;
    2) do_config_embed_flow ;;
    3) DRAFT_CONFIG_LLM=Y do_config_llm_flow ;;
    4) DRAFT_BUILD_RAG=Y do_build_rag_flow ;;
    5) DRAFT_START_UI=Y do_start_ui_flow; exit 0 ;;
    6) printf "${D}Done.${N}\n"; exit 0 ;;
    *) printf "${D}Invalid.${N}\n" ;;
  esac
  echo ""
done
