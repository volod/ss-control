"""Generate evaluation secrets into the run directory. Never commit these values."""

import json
import os
import secrets
from pathlib import Path
from typing import Any


def _token(nbytes: int = 24) -> str:
    return secrets.token_urlsafe(nbytes)


def generate_secrets() -> dict[str, str]:
    """Return a fresh secret map for one evaluation run."""
    password = _token(18)
    return {
        "admin_user": "eval-operator",
        "admin_password": password,
        "admin_email": "eval@ss-control.test",
        "postgres_password": _token(18),
        "keycloak_admin_password": _token(18),
        "client_secret": _token(24),
        "grafana_client_secret": "",
        "nodered_client_secret": "",
        "chirpstack_client_secret": "",
        "oauth2_client_secret": "",
        "oauth2_cookie_secret": secrets.token_hex(16),
        "authelia_jwt_secret": secrets.token_hex(32),
        "authelia_session_secret": secrets.token_hex(32),
        "authelia_storage_key": secrets.token_hex(32),
        "authelia_hmac_secret": secrets.token_hex(32),
        "step_ca_password": _token(18),
        "step_provisioner": "ss-control-eval",
        "grafana_admin_password": password,
        "nodered_credential_secret": secrets.token_hex(16),
        "chirpstack_api_secret": secrets.token_hex(16),
        "openremote_admin_password": _token(18),
        "mqtt_client_name": "eval-mqtt-client",
    }


def write_secrets(path: Path, secrets_map: dict[str, str]) -> None:
    """Write JSON secrets with mode 0o600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(secrets_map, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def load_secrets(path: Path) -> dict[str, Any]:
    """Read secrets JSON from a run directory."""
    return json.loads(path.read_text(encoding="utf-8"))
