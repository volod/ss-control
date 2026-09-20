"""Production image pins and public hostname helpers."""

from dataclasses import dataclass, field
from typing import Any

DEFAULT_DOMAIN = "ss-control.test"
COMPOSE_PROJECT = "ss-control"
COMPOSE_NETWORK = "ss-control"
HTTP_PORT = 80
HTTPS_PORT = 443
MQTT_TLS_PORT = 8883
STEP_CA_PORT = 9000
CERT_NOT_AFTER = "2160h"
PROBE_TIMEOUT_SEC = 45
COMPOSE_WAIT_SEC = 240

# Pins match the evaluation that selected this stack. Bump only with a re-run.
IMAGES = {
    "caddy": "caddy:2.9.1-alpine",
    "authelia": "authelia/authelia:4.39.4",
    "step_ca": "smallstep/step-ca:0.28.4",
    "step_cli": "smallstep/step-cli:0.28.3",
    "grafana": "grafana/grafana:11.6.3",
    "nodered": "nodered/node-red:4.0.9",
    "mosquitto": "eclipse-mosquitto:2.0.21",
    "prometheus": "prom/prometheus:v2.55.1",
    "cadvisor": "gcr.io/cadvisor/cadvisor:v0.49.1",
}

PUBLIC_HOSTS = (
    "grafana",
    "auth",
    "nodered",
    "chirpstack",
    "video",
    "frigate",
    "fusion",
    "prometheus",
    "registry",
)


def public_host(name: str, domain: str = DEFAULT_DOMAIN) -> str:
    """Return `{name}.{domain}`."""
    return f"{name}.{domain}"


def public_url(name: str, domain: str = DEFAULT_DOMAIN) -> str:
    """HTTPS origin for a named ingress host (port 443 omitted)."""
    return f"https://{public_host(name, domain)}"


@dataclass
class ProbeResult:
    """Pass or fail for one named check."""

    name: str
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class ProbeReport:
    """Integration probe outcomes for a running stack."""

    probes: list[ProbeResult] = field(default_factory=list)

    def passed(self) -> bool:
        return bool(self.probes) and all(item.passed for item in self.probes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed(),
            "probes": [item.as_dict() for item in self.probes],
        }
