"""Bring the production control-plane stack up and down."""

import logging
import subprocess
import time
from pathlib import Path

import httpx

from ss_control.stack.ca import (
    ensure_leaf_duration,
    hash_authelia_password,
    issue_stack_certs,
    prepare_ca_dirs,
)
from ss_control.stack.compose import (
    ComposeError,
    compose_env,
    published_host_ports,
    run_compose,
    write_compose_env,
)
from ss_control.stack.dns import install_stack_dns
from ss_control.stack.models import (
    COMPOSE_PROJECT,
    COMPOSE_WAIT_SEC,
    DEFAULT_DOMAIN,
    ProbeReport,
    public_url,
)
from ss_control.stack.paths import compose_file, data_root, project_root, secrets_path
from ss_control.stack.probes import (
    default_report_path,
    probe_grafana_oidc,
    probe_mqtt,
    probe_ports,
    write_report,
)
from ss_control.stack.render import write_authelia_runtime, write_hosts_snippet
from ss_control.stack.secrets import load_or_create_secrets, load_secrets
from ss_control.stack.tls import tls_verify

_LOG = logging.getLogger(__name__)


def compose_env_path(data_dir: Path | None = None) -> Path:
    """Runtime compose env file under `$DATA_DIR/ss-control`."""
    return (data_dir or data_root()) / "compose.env"


def prepare_runtime(*, force_secrets: bool = False) -> tuple[Path, dict[str, str], Path]:
    """Create secrets, Authelia config, and compose.env. Return data, secrets, env file."""
    data_dir = data_root()
    data_dir.mkdir(parents=True, exist_ok=True)
    prepare_ca_dirs(data_dir)
    secrets = load_or_create_secrets(secrets_path(), force=force_secrets)
    domain = secrets.get("SS_CONTROL_DOMAIN", DEFAULT_DOMAIN)
    password_hash = hash_authelia_password(secrets["ADMIN_PASSWORD"])
    write_authelia_runtime(
        data_dir / "authelia",
        secrets,
        password_hash=password_hash,
        domain=domain,
    )
    write_hosts_snippet(data_dir / "hosts.snippet", domain)
    env = compose_env(data_dir=data_dir, secrets=secrets)
    env_file = compose_env_path(data_dir)
    write_compose_env(env_file, env)
    return data_dir, secrets, env_file


def up(*, force_certs: bool = False) -> Path:
    """Start step-ca, issue certs, then start the remaining services."""
    data_dir, secrets, env_file = prepare_runtime()
    run_compose(env_file, ["up", "-d", "--wait", "--wait-timeout", "180", "step-ca"])
    if ensure_leaf_duration(data_dir / "step-ca"):
        run_compose(env_file, ["restart", "step-ca"])
        run_compose(env_file, ["up", "-d", "--wait", "--wait-timeout", "120", "step-ca"])
    issue_stack_certs(
        data_dir=data_dir,
        domain=secrets.get("SS_CONTROL_DOMAIN", DEFAULT_DOMAIN),
        password=secrets["STEP_CA_PASSWORD"],
        provisioner=secrets["STEP_PROVISIONER"],
        mqtt_client=secrets["MQTT_CLIENT_NAME"],
        force=force_certs,
    )
    run_compose(env_file, ["up", "-d", "--remove-orphans"])
    _wait_grafana(secrets, data_dir / "certs" / "root_ca.crt")
    return env_file


def down(*, volumes: bool = False) -> None:
    """Stop the compose project. Certs and `.env.secrets` stay on disk."""
    env_file = compose_env_path()
    args = ["down", "--remove-orphans"]
    if volumes:
        args.append("-v")
    if env_file.is_file():
        run_compose(env_file, args, check=False)
        return
    subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            COMPOSE_PROJECT,
            "-f",
            str(compose_file()),
            *args,
        ],
        check=False,
        cwd=str(project_root()),
        timeout=120,
    )


def probe() -> ProbeReport:
    """Run acceptance probes against the running stack."""
    secrets = load_secrets(secrets_path())
    data_dir = data_root()
    env_file = compose_env_path(data_dir)
    root_ca = data_dir / "certs" / "root_ca.crt"
    report = ProbeReport()
    report.probes.append(probe_grafana_oidc(secrets, root_ca=root_ca))
    report.probes.extend(probe_mqtt(data_dir / "certs", secrets["MQTT_CLIENT_NAME"]))
    report.probes.append(probe_ports(published_host_ports(env_file)))
    write_report(report, default_report_path())
    return report


def _wait_grafana(secrets: dict[str, str], root_ca: Path) -> None:
    domain = secrets.get("SS_CONTROL_DOMAIN", DEFAULT_DOMAIN)
    url = f"{public_url('grafana', domain)}/login"
    install_stack_dns(domain)
    deadline = time.monotonic() + COMPOSE_WAIT_SEC
    last = "not attempted"
    with httpx.Client(verify=tls_verify(root_ca), follow_redirects=False, timeout=5.0) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(url)
                if response.status_code in {200, 302, 303, 307, 308, 401, 403}:
                    return
                last = f"status {response.status_code}"
            except httpx.HTTPError as exc:
                last = str(exc)
            time.sleep(2)
    raise ComposeError(f"timeout waiting for {url}: {last}")
