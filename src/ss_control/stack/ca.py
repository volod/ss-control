"""Issue site-CA certificates with step CLI."""

import contextlib
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from ss_control.eval.ca import CaError, wait_ca_files
from ss_control.stack.models import (
    CERT_NOT_AFTER,
    COMPOSE_NETWORK,
    IMAGES,
    PUBLIC_HOSTS,
    public_host,
)

_LOG = logging.getLogger(__name__)


def _run(argv: list[str], *, timeout_sec: int = 120) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=timeout_sec)
    if result.returncode != 0:
        raise CaError(
            f"{' '.join(argv[:8])} failed: {result.stderr[-1500:] or result.stdout[-1500:]}"
        )
    return result


def hash_authelia_password(password: str) -> str:
    """Hash an operator password with the Authelia image."""
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            IMAGES["authelia"],
            "authelia",
            "crypto",
            "hash",
            "generate",
            "pbkdf2",
            "--variant",
            "sha512",
            "--password",
            password,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("$"):
            return line
        if "Digest:" in line:
            return line.split("Digest:", 1)[1].strip()
    raise RuntimeError("authelia hash output had no digest")


def prepare_ca_dirs(data_dir: Path) -> None:
    """Create runtime directories with container-writable mode."""
    for name in ("step-ca", "certs", "authelia", "grafana", "prometheus", "nodered"):
        path = data_dir / name
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o777)


def ensure_leaf_duration(step_dir: Path, duration: str = CERT_NOT_AFTER) -> bool:
    """Raise the provisioner max leaf duration. Return True when the file changed."""
    ca_json = step_dir / "config" / "ca.json"
    if not ca_json.is_file():
        raise CaError(f"step-ca config missing at {ca_json}")
    payload = json.loads(ca_json.read_text(encoding="utf-8"))
    provisioners = payload.get("authority", {}).get("provisioners", [])
    changed = False
    for item in provisioners:
        claims = item.setdefault("claims", {})
        if claims.get("maxTLSCertDuration") != duration:
            claims["maxTLSCertDuration"] = duration
            claims.setdefault("defaultTLSCertDuration", duration)
            changed = True
    if changed:
        with contextlib.suppress(OSError):
            ca_json.chmod(0o666)
        ca_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return changed


def _copy_root(step_dir: Path, certs_dir: Path) -> Path:
    root = wait_ca_files(step_dir)
    dest = certs_dir / "root_ca.crt"
    shutil.copyfile(root, dest)
    dest.chmod(0o644)
    return dest


def issue_certificate(
    *,
    certs_dir: Path,
    cn: str,
    sans: list[str],
    cert: Path,
    key: Path,
    password: str,
    provisioner: str,
    network: str = COMPOSE_NETWORK,
    not_after: str = CERT_NOT_AFTER,
    force: bool = False,
) -> None:
    """Issue one leaf certificate from the running site CA."""
    if cert.is_file() and key.is_file() and not force:
        return
    password_file = certs_dir / "provisioner.pass"
    if not password_file.is_file():
        password_file.write_text(password + "\n", encoding="utf-8")
        password_file.chmod(0o600)
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
        cert.name if cert.parent == certs_dir else str(cert.relative_to(certs_dir)),
        key.name if key.parent == certs_dir else str(key.relative_to(certs_dir)),
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
        not_after,
    ]
    for san in sans:
        argv.extend(["--san", san])
    _run(argv)
    for path in (cert, key):
        path.chmod(0o644)


def enrol_named(
    *,
    data_dir: Path,
    kind: str,
    name: str,
    sans: list[str],
    password: str,
    provisioner: str,
    force: bool = False,
) -> dict[str, Path]:
    """Issue a Mosquitto client or service certificate under certs/{kind}s/name/."""
    if kind not in {"client", "service"}:
        raise ValueError("kind must be client or service")
    certs_dir = data_dir / "certs"
    dest_dir = certs_dir / f"{kind}s" / name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_dir.chmod(0o755)
    cert = dest_dir / f"{name}.crt"
    key = dest_dir / f"{name}.key"
    # step CLI writes into the mounted certs_dir working copy; use relative names.
    rel_cert = cert.relative_to(certs_dir)
    rel_key = key.relative_to(certs_dir)
    names = [name, *sans]
    issue_certificate(
        certs_dir=certs_dir,
        cn=name,
        sans=names,
        cert=certs_dir / rel_cert,
        key=certs_dir / rel_key,
        password=password,
        provisioner=provisioner,
        force=force,
    )
    root = certs_dir / "root_ca.crt"
    shutil.copyfile(root, dest_dir / "root_ca.crt")
    return {"root": dest_dir / "root_ca.crt", "cert": cert, "key": key}


def issue_stack_certs(
    *,
    data_dir: Path,
    domain: str,
    password: str,
    provisioner: str,
    mqtt_client: str,
    force: bool = False,
) -> dict[str, Path]:
    """Copy the root CA and issue Caddy, Mosquitto, and probe client certificates."""
    certs_dir = data_dir / "certs"
    certs_dir.mkdir(parents=True, exist_ok=True)
    root = _copy_root(data_dir / "step-ca", certs_dir)
    password_file = certs_dir / "provisioner.pass"
    password_file.write_text(password + "\n", encoding="utf-8")
    password_file.chmod(0o600)
    caddy_sans = [domain, "localhost", *[public_host(name, domain) for name in PUBLIC_HOSTS]]
    server = certs_dir / "server.crt"
    server_key = certs_dir / "server.key"
    caddy = certs_dir / "caddy.crt"
    caddy_key = certs_dir / "caddy.key"
    client = certs_dir / "client.crt"
    client_key = certs_dir / "client.key"
    issue_certificate(
        certs_dir=certs_dir,
        cn="mosquitto",
        sans=["mosquitto", "localhost"],
        cert=server,
        key=server_key,
        password=password,
        provisioner=provisioner,
        force=force,
    )
    issue_certificate(
        certs_dir=certs_dir,
        cn="caddy",
        sans=caddy_sans,
        cert=caddy,
        key=caddy_key,
        password=password,
        provisioner=provisioner,
        force=force,
    )
    issue_certificate(
        certs_dir=certs_dir,
        cn=mqtt_client,
        sans=[mqtt_client],
        cert=client,
        key=client_key,
        password=password,
        provisioner=provisioner,
        force=force,
    )
    return {
        "root": root,
        "server_cert": server,
        "server_key": server_key,
        "caddy_cert": caddy,
        "caddy_key": caddy_key,
        "client_cert": client,
        "client_key": client_key,
    }
