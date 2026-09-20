"""Live probes: Grafana OIDC, MQTT mTLS, published ports."""

import json
import logging
import subprocess
from pathlib import Path

import httpx

from ss_control.eval.http_probe import follow_login
from ss_control.eval.mqtt_probe import mqtt_connect
from ss_control.stack.dns import install_stack_dns
from ss_control.stack.models import (
    COMPOSE_PROJECT,
    DEFAULT_DOMAIN,
    MQTT_TLS_PORT,
    PROBE_TIMEOUT_SEC,
    ProbeReport,
    ProbeResult,
    public_host,
    public_url,
)
from ss_control.stack.paths import data_root
from ss_control.stack.tls import tls_verify

_LOG = logging.getLogger(__name__)
_GRAFANA_NEEDLES = ("grafana-app", "sidemenu", "logout", "grafana")


def mosquitto_ip(container: str | None = None) -> str:
    """Return the Mosquitto container IPv4 on the compose network."""
    name = container or f"{COMPOSE_PROJECT}-mosquitto-1"
    result = subprocess.run(
        [
            "docker",
            "inspect",
            "-f",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            name,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    ip = (result.stdout or "").strip()
    if result.returncode != 0 or not ip:
        raise RuntimeError(f"mosquitto ip: {result.stderr or result.stdout}")
    return ip.split()[0]


def probe_grafana_oidc(
    secrets: dict[str, str],
    *,
    root_ca: Path,
) -> ProbeResult:
    """Follow Authelia login until Grafana serves the authenticated app."""
    domain = secrets.get("SS_CONTROL_DOMAIN", DEFAULT_DOMAIN)
    install_stack_dns(domain)
    url = f"{public_url('grafana', domain)}/login"
    try:
        with httpx.Client(
            verify=tls_verify(root_ca),
            follow_redirects=True,
            timeout=PROBE_TIMEOUT_SEC,
        ) as client:
            result = follow_login(
                client,
                url,
                username=secrets["ADMIN_USER"],
                password=secrets["ADMIN_PASSWORD"],
                success_needles=_GRAFANA_NEEDLES,
                success_host=public_host("grafana", domain),
            )
    except httpx.HTTPError as exc:
        return ProbeResult("oidc_grafana", False, f"{type(exc).__name__}: {exc}")
    return ProbeResult("oidc_grafana", result.passed, result.detail)


def probe_mqtt(certs_dir: Path, client_name: str) -> list[ProbeResult]:
    """CONNECT with a site-CA client cert, then without one."""
    host = mosquitto_ip()
    root = certs_dir / "root_ca.crt"
    ok, detail = mqtt_connect(
        host,
        MQTT_TLS_PORT,
        client_id=f"{client_name}-ok",
        ca_file=root,
        cert_file=certs_dir / "client.crt",
        key_file=certs_dir / "client.key",
    )
    accept = ProbeResult("mtls_accept", ok, detail)
    bad, bad_detail = mqtt_connect(
        host,
        MQTT_TLS_PORT,
        client_id=f"{client_name}-bad",
        ca_file=root,
    )
    reject = ProbeResult(
        "mtls_reject",
        not bad,
        "rejected without client cert" if not bad else bad_detail,
    )
    return [accept, reject]


def probe_ports(published: dict[str, list[int]]) -> ProbeResult:
    """Pass when this compose project publishes only 80 and 443."""
    services = {name: ports for name, ports in published.items() if ports}
    if set(services) != {"caddy"}:
        return ProbeResult(
            "published_ports",
            False,
            f"services with host ports: {json.dumps(services, sort_keys=True)}",
        )
    ports = set(services["caddy"])
    if ports != {80, 443}:
        return ProbeResult("published_ports", False, f"caddy host ports {sorted(ports)}")
    return ProbeResult("published_ports", True, "caddy 80 and 443")


def write_report(report: ProbeReport, path: Path) -> None:
    """Write probe JSON with mode 0o644."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8")


def default_report_path() -> Path:
    """`$DATA_DIR/ss-control/probe/result.json`."""
    return data_root() / "probe" / "result.json"
