"""MQTT CONNECT over TLS for the mTLS probe (stdlib only)."""

import socket
import ssl
import struct
from pathlib import Path

PROTOCOL_NAME = b"MQTT"
PROTOCOL_LEVEL = 4
CONNECT_FLAGS = 0x02  # clean session
KEEPALIVE_SEC = 10
CONNACK_OK = 0


def encode_connect(client_id: str) -> bytes:
    """Return a MQTT 3.1.1 CONNECT packet."""
    ident = client_id.encode("utf-8")
    payload = struct.pack("!H", len(ident)) + ident
    variable = (
        struct.pack("!H", len(PROTOCOL_NAME))
        + PROTOCOL_NAME
        + bytes([PROTOCOL_LEVEL, CONNECT_FLAGS])
        + struct.pack("!H", KEEPALIVE_SEC)
    )
    remaining = variable + payload
    header = bytes([0x10]) + _encode_remaining(len(remaining))
    return header + remaining


def _encode_remaining(length: int) -> bytes:
    out = bytearray()
    while True:
        digit = length % 128
        length //= 128
        if length:
            digit |= 0x80
        out.append(digit)
        if not length:
            return bytes(out)


def mqtt_connect(
    host: str,
    port: int,
    *,
    client_id: str,
    ca_file: Path,
    cert_file: Path | None = None,
    key_file: Path | None = None,
    timeout_sec: float = 8.0,
) -> tuple[bool, str]:
    """TLS MQTT CONNECT. Returns (success, detail)."""
    ctx = ssl.create_default_context(cafile=str(ca_file))
    ctx.check_hostname = False
    if cert_file is not None and key_file is not None:
        ctx.load_cert_chain(certfile=str(cert_file), keyfile=str(key_file))
    try:
        raw = socket.create_connection((host, port), timeout=timeout_sec)
    except OSError as exc:
        return False, f"tcp: {exc}"
    try:
        tls = ctx.wrap_socket(raw, server_hostname=host)
    except ssl.SSLError as exc:
        raw.close()
        return False, f"tls: {exc}"
    try:
        tls.sendall(encode_connect(client_id))
        header = tls.recv(4)
        if len(header) < 4 or header[0] != 0x20:
            return False, f"bad connack header {header!r}"
        code = header[3] if len(header) > 3 else 255
        if code != CONNACK_OK:
            return False, f"connack return code {code}"
        return True, "connack 0"
    except OSError as exc:
        return False, f"mqtt: {exc}"
    finally:
        tls.close()
