#!/usr/bin/env bash
# draft venv activation banner: "Draft" in figlet-style ASCII art (light blue), PWD, tracked repos.
# Sourced from .venv/bin/activate after install_venv_banner.sh is run.

[ -z "${VIRTUAL_ENV:-}" ] && return 0

# Project root: parent of .venv
_DRAFT_PROJECT_ROOT="${VIRTUAL_ENV%/.venv}"
[ "$_DRAFT_PROJECT_ROOT" = "$VIRTUAL_ENV" ] && _DRAFT_PROJECT_ROOT="$(cd "$(dirname "$VIRTUAL_ENV")" && pwd)"

# Light blue (bright cyan)
LB='\033[1;96m'
N='\033[0m'

printf '\n'
printf "${LB}"
printf ' ____             __ _   \n'
printf '|  _ \\ _ __ __ _ / _| |_ \n'
printf '| | | | '\''__/ _` | |_| __|\n'
printf '| |_| | | | (_| |  _| |_ \n'
printf '|____/|_|  \\__,_|_|  \\__|\n'
printf "${N}\n"

# Current working directory (path only, no "CWD" label)
printf '  %s\n' "${PWD:-$(pwd)}"

# Tracked sources from sources.yaml: [ github/name | local directory/name ]
_SOURCES_YAML="${_DRAFT_PROJECT_ROOT}/sources.yaml"
if [ -f "$_SOURCES_YAML" ]; then
  _list=$(awk '
    /^[[:space:]]{2,}[A-Za-z0-9_.-]+[[:space:]]*:[[:space:]]*$/ {
      n = $1; gsub(/^[[:space:]]+|[[:space:]]*:[[:space:]]*$/, "", n);
      if (n != "repos" && n != "source") name = n;
      next;
    }
    /^[[:space:]]+source:[[:space:]]/ && name != "" {
      path = $0; gsub(/^[[:space:]]+source:[[:space:]]*/, "", path);
      if (path ~ /^https?:\/\/github\.com\/|^git@github\.com:/)
        printf "github/%s", name;
      else
        printf "local directory/%s", name;
      name = "";
      printf "\n";
      next;
    }
  ' "$_SOURCES_YAML" 2>/dev/null | tr '\n' ',' | sed 's/,$//;s/,/, /g' || true)
  if [ -n "$_list" ]; then
    printf '  Document tracking sources : [ %s ]\n' "$_list"
  fi
fi
printf '\n'

unset _DRAFT_PROJECT_ROOT _SOURCES_YAML _list LB N
