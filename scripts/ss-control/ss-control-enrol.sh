#!/usr/bin/env bash
# Issue a site-CA certificate for an MQTT client or a service.
#
# Usage:
#   ./scripts/ss-control/ss-control-enrol.sh client mqtt-sensor-01
#   ./scripts/ss-control/ss-control-enrol.sh service fusion-rt --san fusion-rt --san localhost

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../shared/common.sh"
ssc_load_env

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "$#" -lt 2 ]]; then
  cat <<'EOF'
Usage: ./scripts/ss-control/ss-control-enrol.sh <client|service> <name> [--san NAME] [--force]

Requires a running stack (`make up`) so step-ca can sign the certificate.
Writes `$DATA_DIR/ss-control/certs/{clients,services}/<name>/`.
EOF
  exit 0
fi

PY="${PROJECT_ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: ${PY} is missing. Run: make bootstrap" >&2
  exit 1
fi

exec "$PY" -m ss_control.stack enrol "$@"
