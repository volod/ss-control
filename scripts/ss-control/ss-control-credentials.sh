#!/usr/bin/env bash
# Generate or print ss-control `.env.secrets`.
#
# Usage:
#   ./scripts/ss-control/ss-control-credentials.sh
#   ./scripts/ss-control/ss-control-credentials.sh --list
#   ./scripts/ss-control/ss-control-credentials.sh --force

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../shared/common.sh"
ssc_load_env

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: ./scripts/ss-control/ss-control-credentials.sh [--list] [--force]

Generates `.env.secrets` when missing (mode 0600).
--list prints the operator summary.
--force overwrites an existing secrets file.
EOF
  exit 0
fi

PY="${PROJECT_ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: ${PY} is missing. Run: make bootstrap" >&2
  exit 1
fi

exec "$PY" -m ss_control.stack credentials "$@"
