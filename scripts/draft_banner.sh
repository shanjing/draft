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

# Tracked repos from repos.yaml (repo names only)
_REPOS_YAML="${_DRAFT_PROJECT_ROOT}/repos.yaml"
if [ -f "$_REPOS_YAML" ]; then
  _repos=$(grep -E '^[[:space:]]{2,}[A-Za-z0-9_.-]+[[:space:]]*:[[:space:]]*$' "$_REPOS_YAML" 2>/dev/null | sed -E 's/^[[:space:]]+//;s/[[:space:]]*:[[:space:]]*$//' | grep -v -E '^(repos|source)$' || true)
  if [ -n "$_repos" ]; then
    printf '  %s\n' "tracking repos: $_repos"
  fi
fi
printf '\n'

unset _DRAFT_PROJECT_ROOT _REPOS_YAML _repos LB N
