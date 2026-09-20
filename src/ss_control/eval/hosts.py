"""Resolve evaluation hostnames to loopback without editing /etc/hosts."""

import socket
from collections.abc import Sequence

from ss_control.eval.models import EVAL_DOMAIN

_original_getaddrinfo = socket.getaddrinfo
_installed = False


def _is_eval_host(host: str) -> bool:
    return host == EVAL_DOMAIN or host.endswith(f".{EVAL_DOMAIN}")


def _patched_getaddrinfo(
    host: str | bytes | None,
    port: str | int | None,
    family: int = 0,
    type: int = 0,
    proto: int = 0,
    flags: int = 0,
) -> list[tuple]:
    if isinstance(host, str) and _is_eval_host(host):
        host = "127.0.0.1"
        if family == 0:
            family = socket.AF_INET
    return _original_getaddrinfo(host, port, family, type, proto, flags)


def install_eval_dns() -> None:
    """Send `*.ss-control.test` to 127.0.0.1 for this process."""
    global _installed
    if _installed:
        return
    socket.getaddrinfo = _patched_getaddrinfo  # type: ignore[assignment]
    _installed = True


def extra_hosts(names: Sequence[str]) -> list[str]:
    """Compose extra_hosts entries using the Docker host gateway."""
    return [f"{name}:host-gateway" for name in names]
