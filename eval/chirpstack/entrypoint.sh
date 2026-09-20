#!/bin/sh
# Install the eval site CA so rustls trusts Caddy, then start ChirpStack.
set -e
if [ -f /certs/root_ca.crt ]; then
  mkdir -p /usr/local/share/ca-certificates
  cp /certs/root_ca.crt /usr/local/share/ca-certificates/ss-control.crt
  if command -v update-ca-certificates >/dev/null 2>&1; then
    update-ca-certificates
  else
    cat /certs/root_ca.crt >> /etc/ssl/certs/ca-certificates.crt
  fi
fi
exec /usr/bin/chirpstack "$@"
