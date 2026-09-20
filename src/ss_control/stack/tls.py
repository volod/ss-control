"""TLS helpers for HTTPS probes against the site CA."""

import ssl
from pathlib import Path


def tls_verify(ca_file: Path | None) -> ssl.SSLContext | bool:
    """Return an SSLContext pinned to the site CA, or False when the file is missing."""
    if ca_file is None or not ca_file.is_file():
        return False
    return ssl.create_default_context(cafile=str(ca_file))
