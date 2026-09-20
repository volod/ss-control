"""Docker Compose helpers for the production stack."""

import json
import logging
import subprocess
from collections.abc import Sequence
from pathlib import Path

from ss_control.eval.envfile import write_env_file
from ss_control.stack.models import (
    COMPOSE_NETWORK,
    COMPOSE_PROJECT,
    DEFAULT_DOMAIN,
    HTTP_PORT,
    HTTPS_PORT,
    IMAGES,
    public_url,
)
from ss_control.stack.paths import compose_file, project_root

_LOG = logging.getLogger(__name__)


class ComposeError(RuntimeError):
    """A docker compose command failed."""


def compose_env(
    *,
    data_dir: Path,
    secrets: dict[str, str],
    bind: str = "0.0.0.0",
    http_port: int = HTTP_PORT,
    https_port: int = HTTPS_PORT,
) -> dict[str, str]:
    """Environment for compose variable substitution."""
    domain = secrets.get("SS_CONTROL_DOMAIN", DEFAULT_DOMAIN)
    grafana = public_url("grafana", domain)
    nodered = public_url("nodered", domain)
    auth = public_url("auth", domain)
    return {
        "COMPOSE_PROJECT_NAME": COMPOSE_PROJECT,
        "SS_CONTROL_DOMAIN": domain,
        "SS_CONTROL_BIND": bind,
        "SS_CONTROL_HTTP_PORT": str(http_port),
        "SS_CONTROL_HTTPS_PORT": str(https_port),
        "SS_CONTROL_DATA": str(data_dir),
        "SS_CONTROL_NETWORK": COMPOSE_NETWORK,
        "SS_VIDEO_UI_UPSTREAM": "upstream-stub:8080",
        "FRIGATE_UPSTREAM": "upstream-stub:8080",
        "CHIRPSTACK_UPSTREAM": "upstream-stub:8080",
        "FUSION_UPSTREAM": "upstream-stub:8080",
        "CADDY_IMAGE": IMAGES["caddy"],
        "AUTHELIA_IMAGE": IMAGES["authelia"],
        "STEP_CA_IMAGE": IMAGES["step_ca"],
        "GRAFANA_IMAGE": IMAGES["grafana"],
        "MOSQUITTO_IMAGE": IMAGES["mosquitto"],
        "PROMETHEUS_IMAGE": IMAGES["prometheus"],
        "CADVISOR_IMAGE": IMAGES["cadvisor"],
        "ADMIN_USER": secrets["ADMIN_USER"],
        "ADMIN_PASSWORD": secrets["ADMIN_PASSWORD"],
        "GRAFANA_CLIENT_SECRET": secrets["GRAFANA_CLIENT_SECRET"],
        "NODERED_CLIENT_SECRET": secrets["NODERED_CLIENT_SECRET"],
        "STEP_CA_PASSWORD": secrets["STEP_CA_PASSWORD"],
        "STEP_PROVISIONER": secrets["STEP_PROVISIONER"],
        "NODERED_CREDENTIAL_SECRET": secrets["NODERED_CREDENTIAL_SECRET"],
        "GRAFANA_ROOT_URL": grafana,
        "OIDC_AUTH_URL": f"{auth}/api/oidc/authorization",
        "OIDC_TOKEN_URL": "http://authelia:9091/api/oidc/token",
        "OIDC_USERINFO_URL": "http://authelia:9091/api/oidc/userinfo",
        "NODERED_OIDC_ISSUER": auth,
        "NODERED_CALLBACK_URL": f"{nodered}/auth/strategy/callback",
    }


def write_compose_env(path: Path, env: dict[str, str]) -> None:
    """Write the compose env file used by `docker compose --env-file`."""
    write_env_file(path, env)


def compose_argv(env_file: Path) -> list[str]:
    """Return the base docker compose argv."""
    return [
        "docker",
        "compose",
        "-p",
        COMPOSE_PROJECT,
        "--env-file",
        str(env_file),
        "-f",
        str(compose_file()),
    ]


def run_compose(
    env_file: Path,
    args: Sequence[str],
    *,
    timeout_sec: int = 600,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run `docker compose ...` from the project root."""
    argv = [*compose_argv(env_file), *args]
    _LOG.info("compose %s", " ".join(args))
    result = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        cwd=str(project_root()),
    )
    if check and result.returncode != 0:
        raise ComposeError(
            f"compose {' '.join(args)} failed ({result.returncode}): {result.stderr[-3000:]}"
        )
    return result


def published_host_ports(env_file: Path) -> dict[str, list[int]]:
    """Return published host TCP ports per service from `docker compose ps`."""
    result = run_compose(env_file, ["ps", "--format", "json"])
    rows: list[dict] = []
    text = result.stdout.strip()
    if text.startswith("["):
        rows = json.loads(text)
    else:
        for line in text.splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    ports: dict[str, list[int]] = {}
    for row in rows:
        service = str(row.get("Service") or row.get("Name") or "")
        publishers = row.get("Publishers") or []
        found: list[int] = []
        for item in publishers:
            published = item.get("PublishedPort") or 0
            protocol = str(item.get("Protocol") or "tcp").lower()
            if published and protocol == "tcp":
                found.append(int(published))
        if found:
            ports[service] = sorted(set(found))
    return ports
