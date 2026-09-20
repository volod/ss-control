"""Generate and load `.env.secrets` for the production stack."""

import os
import secrets
from pathlib import Path

from ss_control.eval.envfile import escape_env
from ss_control.stack.models import DEFAULT_DOMAIN

_SECRET_KEYS = (
    "ADMIN_PASSWORD",
    "GRAFANA_CLIENT_SECRET",
    "CHIRPSTACK_CLIENT_SECRET",
    "NODERED_CLIENT_SECRET",
    "AUTHELIA_JWT_SECRET",
    "AUTHELIA_SESSION_SECRET",
    "AUTHELIA_STORAGE_KEY",
    "AUTHELIA_HMAC_SECRET",
    "STEP_CA_PASSWORD",
    "NODERED_CREDENTIAL_SECRET",
)


def _token(nbytes: int = 24) -> str:
    return secrets.token_urlsafe(nbytes)


def generate_secrets() -> dict[str, str]:
    """Return a fresh secret map. Never log these values."""
    password = _token(18)
    return {
        "SS_CONTROL_DOMAIN": DEFAULT_DOMAIN,
        "ADMIN_USER": "operator",
        "ADMIN_PASSWORD": password,
        "ADMIN_EMAIL": f"operator@{DEFAULT_DOMAIN}",
        "GRAFANA_CLIENT_SECRET": _token(24),
        "CHIRPSTACK_CLIENT_SECRET": _token(24),
        "NODERED_CLIENT_SECRET": _token(24),
        "AUTHELIA_JWT_SECRET": secrets.token_hex(32),
        "AUTHELIA_SESSION_SECRET": secrets.token_hex(32),
        "AUTHELIA_STORAGE_KEY": secrets.token_hex(32),
        "AUTHELIA_HMAC_SECRET": secrets.token_hex(32),
        "STEP_CA_PASSWORD": _token(18),
        "STEP_PROVISIONER": "ss-control",
        "NODERED_CREDENTIAL_SECRET": secrets.token_hex(16),
        "MQTT_CLIENT_NAME": "mqtt-probe",
    }


def write_env_secrets(path: Path, values: dict[str, str]) -> None:
    """Write KEY=value lines with mode 0o600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={escape_env(value)}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a KEY=value file, ignoring comments and blank lines."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.replace("$$", "$")
    return values


def load_secrets(path: Path) -> dict[str, str]:
    """Load secrets, requiring the generated password keys."""
    values = parse_env_file(path)
    missing = [key for key in _SECRET_KEYS if not values.get(key)]
    if missing:
        raise ValueError("missing secrets: " + ", ".join(missing))
    values.setdefault("SS_CONTROL_DOMAIN", DEFAULT_DOMAIN)
    values.setdefault("ADMIN_USER", "operator")
    values.setdefault("ADMIN_EMAIL", f"operator@{values['SS_CONTROL_DOMAIN']}")
    values.setdefault("STEP_PROVISIONER", "ss-control")
    values.setdefault("MQTT_CLIENT_NAME", "mqtt-probe")
    return values


def load_or_create_secrets(path: Path, *, force: bool = False) -> dict[str, str]:
    """Create `.env.secrets` when missing, otherwise load it."""
    if path.is_file() and not force:
        return load_secrets(path)
    values = generate_secrets()
    write_env_secrets(path, values)
    return values


def credentials_summary(values: dict[str, str]) -> str:
    """Operator-facing summary that names URLs and the admin user, not every secret."""
    domain = values.get("SS_CONTROL_DOMAIN", DEFAULT_DOMAIN)
    user = values.get("ADMIN_USER", "operator")
    lines = [
        "ss-control credentials",
        f"  domain: {domain}",
        f"  grafana: https://grafana.{domain}/",
        f"  nodered: https://nodered.{domain}/ (admins group)",
        f"  auth: https://auth.{domain}/",
        f"  admin user: {user}",
        f"  admin password: {values.get('ADMIN_PASSWORD', '')}",
        "  secrets file: .env.secrets (mode 0600)",
        "  browser DNS: append $DATA_DIR/ss-control/hosts.snippet to /etc/hosts",
    ]
    return "\n".join(lines) + "\n"
