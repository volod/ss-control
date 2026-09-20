"""Run probes against a live candidate stack."""

import logging
from urllib.parse import parse_qs, urlparse

import httpx

from ss_control.eval.envfile import authorize_url, oidc_urls
from ss_control.eval.http_probe import (
    audit_from_logs,
    follow_login,
    probe_anonymous_denied,
    probe_authed_ok,
)
from ss_control.eval.jwt_probe import probe_jwt
from ss_control.eval.models import (
    MQTT_TLS_PORT,
    OPENREMOTE_HTTPS_PORT,
    Candidate,
    ProbeResult,
    public_host,
    public_url,
)
from ss_control.eval.mqtt_probe import mqtt_connect

_LOG = logging.getLogger(__name__)
_AUDIT_NEEDLES = (
    "login",
    "authentication",
    "successful authentication",
    "AUTHENTICATE",
    "type=LOGIN",
    "oauth2",
)


def run_probes(
    candidate: Candidate,
    *,
    client: httpx.Client,
    secrets: dict[str, str],
    certs: dict[str, object],
    logs: dict[str, str],
) -> list[ProbeResult]:
    """SSO, forward-auth, JWT, mTLS, audit, and composition operator needs."""
    results: list[ProbeResult] = []
    user = secrets["admin_user"]
    password = secrets["admin_password"]
    urls = oidc_urls(candidate.idp)

    if candidate.baseline == "openremote":
        results.append(
            follow_login(
                client,
                f"https://{secrets.get('or_host', 'auth.ss-control.test')}:{OPENREMOTE_HTTPS_PORT}/",
                username="admin",
                password=secrets["openremote_admin_password"],
                success_needles=("openremote", "manager", "keycloak"),
            )
        )
        results[-1].name = "openremote_ui"
        results.append(probe_jwt_or_skip(client, candidate, secrets, urls))
        results.extend(_mtls(certs, secrets))
        results.append(audit_from_logs(logs, _AUDIT_NEEDLES))
        return results

    results.append(
        follow_login(
            client,
            f"{public_url('grafana')}/login",
            username=user,
            password=password,
            success_needles=("grafana-app", "sidemenu", "logout"),
            success_host=public_host("grafana"),
        )
    )
    results[-1].name = "oidc_grafana"
    results.append(_probe_chirpstack_oidc(client, candidate.idp, user, password))
    results.append(
        follow_login(
            client,
            f"{public_url('nodered')}/auth/strategy",
            username=user,
            password=password,
            success_needles=("red-ui-header", "red-ui-workspace"),
            success_host=public_host("nodered"),
        )
    )
    results[-1].name = "oidc_nodered"

    streamlit = f"{public_url('streamlit')}/streamlit"
    frigate = f"{public_url('frigate')}/frigate"
    results.append(
        probe_anonymous_denied(
            httpx.Client(verify=False, timeout=10, follow_redirects=False),
            streamlit,
            name="forward_auth_streamlit_anon",
        )
    )
    results.append(
        probe_anonymous_denied(
            httpx.Client(verify=False, timeout=10, follow_redirects=False),
            frigate,
            name="forward_auth_frigate_anon",
        )
    )
    fa_start = (
        f"{public_url('streamlit')}/oauth2/start" if candidate.uses_oauth2_proxy else streamlit
    )
    follow_login(
        client,
        fa_start,
        username=user,
        password=password,
        success_needles=(),
    )
    results.append(
        probe_authed_ok(
            client, streamlit, name="forward_auth_streamlit", needles=("streamlit", "ok")
        )
    )
    results.append(
        probe_authed_ok(client, frigate, name="forward_auth_frigate", needles=("frigate", "ok"))
    )
    # Collapse anon+auth into the names the report requires.
    results = _collapse_forward_auth(results)

    results.append(probe_jwt_or_skip(client, candidate, secrets, urls))
    results.extend(_mtls(certs, secrets))
    results.append(audit_from_logs(logs, _AUDIT_NEEDLES))

    token_header = _bearer(client, candidate, secrets, urls)
    results.append(
        _stub_json(
            client, f"{public_url('registry')}/registry/devices", "registry_api", token_header
        )
    )
    results.append(
        _stub_json(
            client, f"{public_url('fusion')}/fusion/incidents", "fusion_incidents", token_header
        )
    )
    return results


def _varint(value: int) -> bytes:
    """Encode an unsigned protobuf varint."""
    out = bytearray()
    remaining = int(value)
    while True:
        byte = remaining & 0x7F
        remaining >>= 7
        if remaining:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _proto_string(field: int, value: str) -> bytes:
    """Encode a protobuf length-delimited string field."""
    data = value.encode("utf-8")
    return bytes([(int(field) << 3) | 2]) + _varint(len(data)) + data


def _grpc_web_frame(payload: bytes) -> bytes:
    return b"\x00" + len(payload).to_bytes(4, "big") + payload


def _grpc_web_payload(body: bytes) -> bytes:
    if len(body) >= 5 and body[0] in (0, 1):
        length = int.from_bytes(body[1:5], "big")
        return body[5 : 5 + length]
    return body


def _proto_strings(payload: bytes) -> list[str]:
    """Extract UTF-8 strings from a protobuf message of string fields."""
    strings: list[str] = []
    index = 0
    while index < len(payload):
        tag = payload[index]
        index += 1
        if (tag & 7) != 2:
            break
        length = 0
        shift = 0
        while index < len(payload):
            byte = payload[index]
            index += 1
            length |= (byte & 0x7F) << shift
            if byte < 0x80:
                break
            shift += 7
        raw = payload[index : index + length]
        index += length
        try:
            strings.append(raw.decode("utf-8"))
        except UnicodeDecodeError:
            continue
    return strings


def _grpc_web_http_urls(body: bytes) -> list[str]:
    """Extract http(s) strings from a grpc-web protobuf frame."""
    return [
        text
        for text in _proto_strings(_grpc_web_payload(body))
        if text.startswith("http://") or text.startswith("https://")
    ]


def oidc_code_state(url: str) -> tuple[str, str]:
    """Read OIDC code and state from a callback URL, including hash routes."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if parsed.fragment:
        fragment = parsed.fragment
        if "?" in fragment:
            fragment = fragment.split("?", 1)[1]
        query = {**parse_qs(fragment), **query}
    code = (query.get("code") or [""])[0]
    state = (query.get("state") or [""])[0]
    return code, state


def _url_from_detail(detail: str) -> str:
    marker = "url="
    if marker not in detail:
        return ""
    return detail.rsplit(marker, 1)[-1].strip()


def _probe_chirpstack_oidc(
    client: httpx.Client, idp: str, username: str, password: str
) -> ProbeResult:
    """Complete ChirpStack OIDC including the gRPC-web code exchange."""
    start = _chirpstack_oidc_start(client, idp)
    code, state = oidc_code_state(start)
    if not (code and state):
        hopped = follow_login(
            client,
            start,
            username=username,
            password=password,
            success_needles=(),
            success_host="",
        )
        landed = _url_from_detail(hopped.detail) or start
        code, state = oidc_code_state(landed)
        if not (code and state):
            return ProbeResult(
                "oidc_chirpstack",
                False,
                hopped.detail or f"no OIDC code at {landed}",
            )
    token, detail = _chirpstack_oidc_token(client, code, state)
    if not token:
        return ProbeResult("oidc_chirpstack", False, detail)
    return ProbeResult("oidc_chirpstack", True, detail)


def _chirpstack_oidc_token(client: httpx.Client, code: str, state: str) -> tuple[str, str]:
    """Exchange the SPA callback code through InternalService.OpenIdConnectLogin."""
    payload = _proto_string(1, code) + _proto_string(2, state)
    try:
        response = client.post(
            f"{public_url('chirpstack')}/api.InternalService/OpenIdConnectLogin",
            content=_grpc_web_frame(payload),
            headers={
                "Content-Type": "application/grpc-web+proto",
                "Accept": "application/grpc-web+proto",
                "X-Grpc-Web": "1",
            },
        )
    except httpx.HTTPError as exc:
        return "", f"{type(exc).__name__}: {exc}"
    grpc_status = response.headers.get("grpc-status", "")
    strings = _proto_strings(_grpc_web_payload(response.content))
    token = next((item for item in strings if len(item) >= 16), "")
    if response.status_code >= 400 or (grpc_status and grpc_status != "0") or not token:
        preview = response.content[:240]
        return "", (
            f"grpc http={response.status_code} grpc-status={grpc_status or 'missing'} "
            f"strings={len(strings)} body={preview!r}"
        )
    return token, f"token_len={len(token)}"


def _chirpstack_oidc_start(client: httpx.Client, idp: str) -> str:
    """Start OIDC from ChirpStack so the callback has a matching CSRF state."""
    base = public_url("chirpstack")
    fallback = authorize_url(idp, "chirpstack", f"{base}/auth/oidc/callback")
    for path in ("/auth/oidc/login", "/oidc/login", "/auth/oidc"):
        try:
            response = client.get(f"{base}{path}")
        except httpx.HTTPError:
            continue
        if response.status_code in {404, 500}:
            continue
        if "error=" in str(response.url).lower():
            continue
        if public_host("chirpstack") not in str(response.url) or response.history:
            return str(response.url)
    try:
        framed = b"\x00\x00\x00\x00\x00"
        response = client.post(
            f"{base}/api.InternalService/OpenIdConnectLogin",
            content=framed,
            headers={
                "Content-Type": "application/grpc-web+proto",
                "Accept": "application/grpc-web+proto",
                "X-Grpc-Web": "1",
            },
        )
        urls = _grpc_web_http_urls(response.content)
        if urls:
            return urls[0]
        haystack = response.content.decode("latin1", errors="ignore")
        marker = "https://"
        found = haystack.find(marker)
        if found >= 0:
            url = haystack[found:].split("\x00", 1)[0].split(" ")[0].strip()
            if url.startswith("https://") and len(url) < 2000:
                return url
        _LOG.warning(
            "chirpstack OpenIdConnectLogin had no URL (status=%s bytes=%s)",
            response.status_code,
            len(response.content),
        )
    except httpx.HTTPError as exc:
        _LOG.warning("chirpstack OpenIdConnectLogin failed: %s", exc)
    return fallback


def probe_jwt_or_skip(
    client: httpx.Client,
    candidate: Candidate,
    secrets: dict[str, str],
    urls: dict[str, str],
) -> ProbeResult:
    authelia = candidate.idp == "authelia"
    return probe_jwt(
        client,
        issuer=urls["OIDC_ISSUER"],
        token_url=urls["OIDC_TOKEN_PUBLIC"],
        jwks_url=urls["OIDC_JWKS_URL"],
        client_id="eval-cli" if candidate.idp != "kanidm" else "grafana",
        client_secret=secrets["client_secret"],
        username=secrets["admin_user"],
        password=secrets["admin_password"],
        scope="groups" if authelia else "openid",
        extra={"audience": "eval-cli"} if authelia else None,
    )


def _bearer(
    client: httpx.Client,
    candidate: Candidate,
    secrets: dict[str, str],
    urls: dict[str, str],
) -> str:
    jwt_result = probe_jwt_or_skip(client, candidate, secrets, urls)
    if not jwt_result.passed:
        return ""
    # Re-fetch a token for the stub; probe_jwt already consumed one. Best-effort.
    from ss_control.eval.jwt_probe import client_credentials_token, password_token

    try:
        extra = {"audience": "eval-cli"} if candidate.idp == "authelia" else None
        return "Bearer " + client_credentials_token(
            client,
            urls["OIDC_TOKEN_PUBLIC"],
            client_id="eval-cli" if candidate.idp != "kanidm" else "grafana",
            client_secret=secrets["client_secret"],
            scope="groups" if candidate.idp == "authelia" else "openid",
            extra=extra,
        )
    except Exception:
        try:
            return "Bearer " + password_token(
                client,
                urls["OIDC_TOKEN_PUBLIC"],
                client_id="eval-cli" if candidate.idp != "kanidm" else "grafana",
                client_secret=secrets["client_secret"],
                username=secrets["admin_user"],
                password=secrets["admin_password"],
            )
        except Exception as exc:
            _LOG.warning("no bearer token for stubs: %s", exc)
            return ""


def _stub_json(client: httpx.Client, url: str, name: str, authorization: str) -> ProbeResult:
    headers = {"Authorization": authorization} if authorization else {}
    try:
        response = client.get(url, headers=headers)
        if response.status_code >= 400:
            return ProbeResult(name, False, f"status={response.status_code}")
        return ProbeResult(name, True, f"status={response.status_code}")
    except httpx.HTTPError as exc:
        return ProbeResult(name, False, str(exc))


def _mtls(certs: dict[str, object], secrets: dict[str, str]) -> list[ProbeResult]:
    from pathlib import Path

    root = Path(str(certs["root"]))
    ok, detail = mqtt_connect(
        "127.0.0.1",
        MQTT_TLS_PORT,
        client_id="eval-ok",
        ca_file=root,
        cert_file=Path(str(certs["client_cert"])),
        key_file=Path(str(certs["client_key"])),
    )
    accept = ProbeResult("mtls_accept", ok, detail)
    bad, bad_detail = mqtt_connect(
        "127.0.0.1",
        MQTT_TLS_PORT,
        client_id="eval-bad",
        ca_file=root,
    )
    reject = ProbeResult(
        "mtls_reject", not bad, "rejected without client cert" if not bad else bad_detail
    )
    _ = secrets
    return [accept, reject]


def _collapse_forward_auth(results: list[ProbeResult]) -> list[ProbeResult]:
    by_name = {item.name: item for item in results}
    kept = [
        item
        for item in results
        if item.name
        not in {
            "forward_auth_streamlit_anon",
            "forward_auth_frigate_anon",
            "forward_auth_streamlit",
            "forward_auth_frigate",
        }
    ]
    for app in ("streamlit", "frigate"):
        anon = by_name.get(f"forward_auth_{app}_anon")
        authed = by_name.get(f"forward_auth_{app}")
        passed = bool(anon and anon.passed and authed and authed.passed)
        detail = f"anon={getattr(anon, 'detail', '')}; auth={getattr(authed, 'detail', '')}"
        kept.append(ProbeResult(f"forward_auth_{app}", passed, detail))
    return kept
