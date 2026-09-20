#!/usr/bin/env bash
# Shared environment bootstrap. Source this file; do not execute it.

ssc_project_root() {
  (cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
}

PROJECT_ROOT="${PROJECT_ROOT:-$(ssc_project_root)}"

ssc_path_device() {
  local path="$1"
  local parent
  while [ -n "$path" ] && [ ! -e "$path" ]; do
    parent="$(dirname "$path")"
    [ "$parent" = "$path" ] && break
    path="$parent"
  done
  [ -e "$path" ] || return 1
  stat -c '%d' "$path" 2>/dev/null || stat -f '%d' "$path" 2>/dev/null
}

# uv hardlinks from its cache by default; across filesystems that fails, so copy only then.
ssc_export_uv_link_mode() {
  local mode="${UV_LINK_MODE:-}"
  if [ -n "$mode" ] && [ "${mode,,}" != "auto" ]; then
    export UV_LINK_MODE
    return 0
  fi

  unset UV_LINK_MODE
  local cache_device
  local root_device
  mkdir -p "$UV_CACHE_DIR"
  cache_device="$(ssc_path_device "$UV_CACHE_DIR")" || cache_device=""
  root_device="$(ssc_path_device "$PROJECT_ROOT/.venv")" || root_device=""
  if [ -n "$cache_device" ] && [ -n "$root_device" ] && [ "$cache_device" != "$root_device" ]; then
    export UV_LINK_MODE=copy
  fi
}

ssc_export_tool_caches() {
  export UV_CACHE_DIR="${UV_CACHE_DIR:-$DATA_DIR/uv-cache}"
  export RUFF_CACHE_DIR="${RUFF_CACHE_DIR:-$DATA_DIR/cache/ruff}"
  export MYPY_CACHE_DIR="${MYPY_CACHE_DIR:-$DATA_DIR/cache/mypy}"
}

# Load .env, resolve DATA_DIR against the project root, and derive every cache from it.
ssc_load_env() {
  if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    . "$PROJECT_ROOT/.env"
    set +a
  fi
  DATA_DIR="${DATA_DIR:-$PROJECT_ROOT/.data}"
  case "$DATA_DIR" in
    /*) ;;
    *) DATA_DIR="$PROJECT_ROOT/${DATA_DIR#./}" ;;
  esac
  export DATA_DIR
  ssc_export_tool_caches
  ssc_export_uv_link_mode
}
