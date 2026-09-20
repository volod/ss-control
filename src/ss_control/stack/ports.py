"""Published-port helpers that work on compose YAML without Docker."""

import re
from pathlib import Path

_PORTS_RE = re.compile(
    r"^  (?P<service>[a-zA-Z0-9._-]+):\s*\n(?:    .+\n)*?    ports:\s*\n(?P<body>(?:      - .+\n)+)",
    re.MULTILINE,
)
_CONTAINER_PORT_RE = re.compile(r":(\d+)\s*$")


def services_with_published_ports(compose_text: str) -> dict[str, list[int]]:
    """Return container ports published by each service in a compose file.

    Host bind and host port may be interpolated (`${SS_CONTROL_HTTPS_PORT:-443}`);
    the last `:N` on each mapping is the container port.
    """
    found: dict[str, list[int]] = {}
    for match in _PORTS_RE.finditer(compose_text):
        service = match.group("service")
        ports: list[int] = []
        for line in match.group("body").splitlines():
            mapping = line.split("-", 1)[-1].strip().strip("\"'")
            port_match = _CONTAINER_PORT_RE.search(mapping)
            if port_match:
                ports.append(int(port_match.group(1)))
        if ports:
            found[service] = ports
    return found


def only_ingress_ports(compose_text: str) -> tuple[bool, str]:
    """Pass when only `caddy` publishes ports, and those ports are 80 and 443."""
    published = services_with_published_ports(compose_text)
    if set(published) != {"caddy"}:
        return False, f"services with ports: {sorted(published)}"
    ports = set(published["caddy"])
    if ports != {80, 443}:
        return False, f"caddy container ports {sorted(ports)}"
    return True, "caddy publishes 80 and 443"


def compose_text(path: Path) -> str:
    """Read a compose file as text."""
    return path.read_text(encoding="utf-8")
