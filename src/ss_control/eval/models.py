"""Candidate definitions and result records."""

from dataclasses import dataclass, field
from typing import Any

EVAL_DOMAIN = "ss-control.test"
# Caddy must listen on the same port the browser puts in Host. In-cluster
# aliases then reach the public HTTPS URLs without a second published port.
PROXY_HTTPS_PORT = 18443
PROXY_HTTP_PORT = 18080
CADDY_LISTEN_HTTPS = PROXY_HTTPS_PORT
CADDY_LISTEN_HTTP = 80
MQTT_TLS_PORT = 19883
OPENREMOTE_HTTPS_PORT = 19443
STEP_CA_PORT = 9000
IDLE_SAMPLE_SEC = 20
PEAK_SAMPLE_SEC = 15
STATS_INTERVAL_SEC = 2
COMPOSE_WAIT_SEC = 240
PROBE_TIMEOUT_SEC = 45

# Images pinned for a repeatable eval. Bump only with a re-run.
IMAGES = {
    "caddy": "caddy:2.9.1-alpine",
    "keycloak": "quay.io/keycloak/keycloak:26.3.3",
    "authelia": "authelia/authelia:4.39.4",
    "kanidm": "kanidm/server:1.6.4",
    "kanidm_tools": "kanidm/tools:1.6.4",
    "step_ca": "smallstep/step-ca:0.28.4",
    "step_cli": "smallstep/step-cli:0.28.3",
    "grafana": "grafana/grafana:11.6.3",
    "nodered": "nodered/node-red:4.0.9",
    "chirpstack": "chirpstack/chirpstack:4.12.1",
    "mosquitto": "eclipse-mosquitto:2.0.21",
    "postgres": "postgres:16-alpine",
    "redis": "redis:7-alpine",
    "oauth2_proxy": "quay.io/oauth2-proxy/oauth2-proxy:v7.8.2",
    "python": "python:3.12-alpine",
    "openremote_proxy": "openremote/proxy:latest",
    "openremote_keycloak": "openremote/keycloak:latest",
    "openremote_manager": "openremote/manager:latest",
    "openremote_postgres": "openremote/postgresql:latest",
}


@dataclass(frozen=True)
class Candidate:
    """One measured stack: identity provider plus operator baseline."""

    id: str
    idp: str
    baseline: str
    uses_oauth2_proxy: bool


CANDIDATES: tuple[Candidate, ...] = (
    Candidate("keycloak-composition", "keycloak", "composition", True),
    Candidate("kanidm-composition", "kanidm", "composition", True),
    Candidate("authelia-composition", "authelia", "composition", False),
    Candidate("openremote-keycloak", "openremote", "openremote", False),
)

CADENCE_REPOS: tuple[tuple[str, str, str], ...] = (
    ("caddy", "caddyserver", "caddy"),
    ("keycloak", "keycloak", "keycloak"),
    ("kanidm", "kanidm", "kanidm"),
    ("authelia", "authelia", "authelia"),
    ("step-ca", "smallstep", "certificates"),
    ("openremote", "openremote", "openremote"),
)


@dataclass
class ProbeResult:
    """Pass or fail for one named check."""

    name: str
    passed: bool
    detail: str = ""


@dataclass
class ResourceSample:
    """Aggregated docker stats for one phase."""

    cpu_pct: float
    rss_mib: float
    per_service: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class CandidateResult:
    """Measurements and probes for one candidate."""

    candidate_id: str
    idle: ResourceSample | None = None
    peak: ResourceSample | None = None
    probes: list[ProbeResult] = field(default_factory=list)
    error: str = ""
    logs_excerpt: str = ""

    def probe_map(self) -> dict[str, ProbeResult]:
        return {item.name: item for item in self.probes}

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "error": self.error,
            "idle": None
            if self.idle is None
            else {
                "cpu_pct": self.idle.cpu_pct,
                "rss_mib": round(self.idle.rss_mib, 1),
                "per_service": self.idle.per_service,
            },
            "peak": None
            if self.peak is None
            else {
                "cpu_pct": self.peak.cpu_pct,
                "rss_mib": round(self.peak.rss_mib, 1),
                "per_service": self.peak.per_service,
            },
            "probes": [
                {"name": item.name, "passed": item.passed, "detail": item.detail}
                for item in self.probes
            ],
        }


def public_host(name: str) -> str:
    """Return `{name}.ss-control.test`."""
    return f"{name}.{EVAL_DOMAIN}"


def public_url(name: str, *, tls: bool = True, port: int | None = None) -> str:
    """Browser URL for a named ingress host."""
    scheme = "https" if tls else "http"
    host_port = PROXY_HTTPS_PORT if tls else PROXY_HTTP_PORT
    if port is not None:
        host_port = port
    return f"{scheme}://{public_host(name)}:{host_port}"
