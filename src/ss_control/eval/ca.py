"""Issue Mosquitto and Kanidm certificates from step-ca."""

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from ss_control.eval.models import EVAL_DOMAIN, IMAGES, public_host

_LOG = logging.getLogger(__name__)


class CaError(RuntimeError):
    """Certificate issuance failed."""


def _run(argv: list[str], *, timeout_sec: int = 120) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=timeout_sec)
    if result.returncode != 0:
        raise CaError(
            f"{' '.join(argv[:6])} failed: {result.stderr[-1500:] or result.stdout[-1500:]}"
        )
    return result


def wait_ca_files(step_dir: Path, timeout_sec: float = 90.0) -> Path:
    """Wait until step-ca has written the root certificate."""
    root = step_dir / "certs" / "root_ca.crt"
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if root.is_file() and root.stat().st_size > 0:
            return root
        time.sleep(1)
    raise CaError(f"step-ca root certificate not found at {root}")


def issue_certs(
    *,
    certs_dir: Path,
    step_dir: Path,
    password: str,
    provisioner: str,
    network: str,
    client_name: str,
) -> dict[str, Path]:
    """Copy the root CA and issue server plus client certificates via step CLI."""
    certs_dir.mkdir(parents=True, exist_ok=True)
    root = wait_ca_files(step_dir)
    dest_root = certs_dir / "root_ca.crt"
    shutil.copyfile(root, dest_root)
    password_file = certs_dir / "provisioner.pass"
    password_file.write_text(password + "\n", encoding="utf-8")
    password_file.chmod(0o600)

    def _issue(cn: str, sans: list[str], cert: Path, key: Path) -> None:
        if cert.is_file() and key.is_file():
            return
        _LOG.info("issuing certificate for %s", cn)
        argv = [
            "docker",
            "run",
            "--rm",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--network",
            network,
            "-e",
            "HOME=/work",
            "-v",
            f"{certs_dir}:/work",
            "-w",
            "/work",
            IMAGES["step_cli"],
            "step",
            "ca",
            "certificate",
            cn,
            cert.name,
            key.name,
            "--ca-url",
            "https://step-ca:9000",
            "--root",
            "root_ca.crt",
            "--provisioner",
            provisioner,
            "--provisioner-password-file",
            password_file.name,
            "--force",
            "--not-after",
            "24h",
        ]
        for san in sans:
            argv.extend(["--san", san])
        _run(argv)

    server_cert = certs_dir / "server.crt"
    server_key = certs_dir / "server.key"
    client_cert = certs_dir / "client.crt"
    client_key = certs_dir / "client.key"
    kanidm_cert = certs_dir / "kanidm.crt"
    kanidm_key = certs_dir / "kanidm.key"
    caddy_cert = certs_dir / "caddy.crt"
    caddy_key = certs_dir / "caddy.key"
    _issue("mosquitto", ["mosquitto"], server_cert, server_key)
    _issue(client_name, [client_name], client_cert, client_key)
    _issue("kanidm", ["kanidm"], kanidm_cert, kanidm_key)
    caddy_sans = [
        EVAL_DOMAIN,
        "localhost",
        public_host("grafana"),
        public_host("chirpstack"),
        public_host("nodered"),
        public_host("streamlit"),
        public_host("frigate"),
        public_host("fusion"),
        public_host("registry"),
        public_host("auth"),
    ]
    _issue("caddy", caddy_sans, caddy_cert, caddy_key)
    for path in (
        dest_root,
        server_cert,
        server_key,
        client_cert,
        client_key,
        kanidm_cert,
        kanidm_key,
        caddy_cert,
        caddy_key,
    ):
        path.chmod(0o644)
    return {
        "root": dest_root,
        "server_cert": server_cert,
        "server_key": server_key,
        "client_cert": client_cert,
        "client_key": client_key,
        "kanidm_cert": kanidm_cert,
        "kanidm_key": kanidm_key,
        "caddy_cert": caddy_cert,
        "caddy_key": caddy_key,
    }
