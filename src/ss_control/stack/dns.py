"""Resolve production hostnames to loopback without editing /etc/hosts."""

import socket

_original_getaddrinfo = socket.getaddrinfo
_installed_domain = ""


def _is_stack_host(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def install_stack_dns(domain: str) -> None:
    """Send `{domain}` and `*.{domain}` to 127.0.0.1 for this process."""
    global _installed_domain
    if _installed_domain == domain:
        return

    def _patched_getaddrinfo(
        host: str | bytes | None,
        port: str | int | None,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple]:
        if isinstance(host, str) and _is_stack_host(host, domain):
            host = "127.0.0.1"
            if family == 0:
                family = socket.AF_INET
        return _original_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = _patched_getaddrinfo  # type: ignore[assignment]
    _installed_domain = domain
