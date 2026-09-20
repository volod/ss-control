"""Bootstrap Kanidm persons, groups, and OAuth2 resource servers."""

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path

from ss_control.eval.models import IMAGES, public_url

_LOG = logging.getLogger(__name__)
_PASSWORD_KEYS = ("new_credential", "new_password", "password")


class KanidmError(RuntimeError):
    """Kanidm bootstrap failed."""


def _run(
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout_sec: int = 120,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        env=env,
        input=input_text,
    )
    if result.returncode != 0:
        raise KanidmError(
            f"{' '.join(argv[:8])} failed ({result.returncode}): "
            f"{(result.stderr or result.stdout)[-2000:]}"
        )
    return result


def _parse_password(blob: str) -> str:
    text = blob.strip()
    start = text.find("{")
    if start >= 0:
        try:
            payload, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            for key in _PASSWORD_KEYS:
                value = payload.get(key)
                if value:
                    return str(value)
    for key in ("new_password", "new_credential", "password"):
        match = re.search(rf'{key}["\s:=]+["\']([^"\']+)', text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    raise KanidmError(f"could not parse recover-account password from: {text[-500:]}")


def wait_kanidm(container: str, timeout_sec: float = 120.0) -> None:
    """Wait until `kanidmd healthcheck` succeeds."""
    deadline = time.monotonic() + timeout_sec
    last = "not attempted"
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "exec", container, "kanidmd", "healthcheck"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return
        last = result.stderr or result.stdout or f"exit {result.returncode}"
        time.sleep(2)
    raise KanidmError(f"kanidm healthcheck timeout: {last[-400:]}")


def recover_password(container: str, account: str) -> str:
    """Reset an account via recover-account and return the generated password."""
    result = _run(
        ["docker", "exec", container, "kanidmd", "recover-account", "-o", "json", account]
    )
    blob = (result.stdout or "") + "\n" + (result.stderr or "")
    return _parse_password(blob)


def _cli_env(home: Path, admin_password: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "KANIDM_URL": "https://kanidm:8443",
            "KANIDM_NAME": "idm_admin",
            "KANIDM_PASSWORD": admin_password,
            "KANIDM_ACCEPT_INVALID_CERTS": "true",
            "KANIDM_SKIP_HOSTNAME_VERIFICATION": "true",
            "KANIDM_OUTPUT": "json",
        }
    )
    return env


def _cli(
    network: str,
    home: Path,
    admin_password: str,
    args: list[str],
    *,
    output_json: bool = True,
) -> subprocess.CompletedProcess[str]:
    output_mode = "json" if output_json else "text"
    argv = [
        "docker",
        "run",
        "--rm",
        "--network",
        network,
        "-e",
        "HOME=/home/kanidm",
        "-e",
        "KANIDM_URL=https://kanidm:8443",
        "-e",
        "KANIDM_NAME=idm_admin",
        "-e",
        f"KANIDM_PASSWORD={admin_password}",
        "-e",
        "KANIDM_ACCEPT_INVALID_CERTS=true",
        "-e",
        "KANIDM_SKIP_HOSTNAME_VERIFICATION=true",
        "-e",
        f"KANIDM_OUTPUT={output_mode}",
        "-v",
        f"{home}:/home/kanidm",
        IMAGES["kanidm_tools"],
        "kanidm",
        *args,
        "-H",
        "https://kanidm:8443",
        "-D",
        "idm_admin",
        "--accept-invalid-certs",
        "--skip-hostname-verification",
        "-o",
        output_mode,
    ]
    _ = _cli_env
    return _run(argv, timeout_sec=90)


def _secret_from_output(blob: str) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", blob).strip()
    start = text.find("{")
    if start >= 0:
        try:
            payload, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            for key in ("secret", "basic_secret", "password"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value
        if isinstance(payload, str) and payload.lower() not in {"success", "ok"}:
            return payload
    skip = ("success", "true", "ok", "null")
    for line in text.splitlines():
        line = line.strip().strip('"')
        if not line or " " in line:
            continue
        lower = line.lower()
        if lower in skip or "warn" in lower or "tls" in lower or "idm_cli" in lower:
            continue
        if len(line) >= 8:
            return line
    raise KanidmError(f"no oauth2 basic secret in: {text[-500:]}")


def bootstrap_kanidm(
    *,
    project: str,
    network: str,
    secrets: dict[str, str],
    data_dir: Path,
) -> dict[str, str]:
    """Create eval-operator, admins group, and OAuth2 clients. Mutates `secrets`."""
    container = f"{project}-kanidm-1"
    wait_kanidm(container)
    admin_password = recover_password(container, "idm_admin")
    time.sleep(1)
    home = data_dir / "kanidm-cli"
    home.mkdir(parents=True, exist_ok=True)
    home.chmod(0o777)
    _cli(network, home, admin_password, ["login"])
    person = secrets["admin_user"]
    _cli(network, home, admin_password, ["person", "create", person, "Eval Operator"])
    _cli(
        network,
        home,
        admin_password,
        ["person", "update", person, "--mail", f"{person}@ss-control.test"],
    )
    _cli(network, home, admin_password, ["group", "create", "admins"])
    _cli(network, home, admin_password, ["group", "add-members", "admins", person])
    person_password = recover_password(container, person)
    secrets["admin_password"] = person_password
    clients = {
        "grafana": (public_url("grafana"), f"{public_url('grafana')}/login/generic_oauth"),
        "chirpstack": (
            public_url("chirpstack"),
            f"{public_url('chirpstack')}/auth/oidc/callback",
        ),
        "nodered": (public_url("nodered"), f"{public_url('nodered')}/auth/strategy"),
        "oauth2-proxy": (
            public_url("streamlit"),
            f"{public_url('streamlit')}/oauth2/callback",
        ),
    }
    extracted: dict[str, str] = {}
    for name, (origin, redirect) in clients.items():
        _cli(
            network,
            home,
            admin_password,
            ["system", "oauth2", "create", name, name, origin],
        )
        _cli(
            network,
            home,
            admin_password,
            ["system", "oauth2", "add-redirect-url", name, redirect],
        )
        if name == "nodered":
            _cli(
                network,
                home,
                admin_password,
                [
                    "system",
                    "oauth2",
                    "add-redirect-url",
                    name,
                    f"{public_url('nodered')}/auth/strategy/callback",
                ],
            )
        if name == "oauth2-proxy":
            _cli(
                network,
                home,
                admin_password,
                [
                    "system",
                    "oauth2",
                    "add-redirect-url",
                    name,
                    f"{public_url('frigate')}/oauth2/callback",
                ],
            )
        _cli(
            network,
            home,
            admin_password,
            [
                "system",
                "oauth2",
                "update-scope-map",
                name,
                "idm_all_persons",
                "openid",
                "profile",
                "email",
                "groups",
            ],
        )
        _cli(
            network,
            home,
            admin_password,
            ["system", "oauth2", "prefer-short-username", name],
        )
        if name in {"chirpstack", "nodered"}:
            _cli(
                network,
                home,
                admin_password,
                ["system", "oauth2", "warning-insecure-client-disable-pkce", name],
            )
        shown = _cli(
            network,
            home,
            admin_password,
            ["system", "oauth2", "show-basic-secret", name],
        )
        blob = (shown.stdout or "") + (shown.stderr or "")
        try:
            extracted[name] = _secret_from_output(blob)
        except KanidmError:
            shown = _cli(
                network,
                home,
                admin_password,
                ["system", "oauth2", "show-basic-secret", name],
                output_json=False,
            )
            extracted[name] = _secret_from_output((shown.stdout or "") + (shown.stderr or ""))
    secrets["grafana_client_secret"] = extracted["grafana"]
    secrets["chirpstack_client_secret"] = extracted["chirpstack"]
    secrets["nodered_client_secret"] = extracted["nodered"]
    secrets["oauth2_client_secret"] = extracted["oauth2-proxy"]
    secrets["client_secret"] = extracted["grafana"]
    _LOG.info("kanidm oauth2 clients created for %s", ", ".join(clients))
    return extracted
