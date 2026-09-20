"""Unit tests for the evaluation harness (no Docker)."""

from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from ss_control.eval.caddyfile import render_caddyfile
from ss_control.eval.cadence import cadence_days
from ss_control.eval.envfile import escape_env, oidc_urls
from ss_control.eval.http_probe import audit_from_logs, parse_login_form
from ss_control.eval.jwt_probe import validator_for_token
from ss_control.eval.models import CANDIDATES, CandidateResult, ProbeResult, ResourceSample
from ss_control.eval.mqtt_probe import encode_connect
from ss_control.eval.report import select_stack
from ss_control.eval.stats import parse_cpu_pct, parse_mem_bytes, summarize_stats


def test_stats_parsers_and_summary() -> None:
    assert parse_cpu_pct("12.5%") == 12.5
    assert abs(parse_mem_bytes("1.5GiB / 16GiB") - 1.5 * 1024 * 1024 * 1024) < 1
    sample = summarize_stats(
        [
            {"Name": "ssce-grafana-1", "CPUPerc": "2.0%", "MemUsage": "100MiB / 1GiB"},
            {"Name": "ssce-caddy-1", "CPUPerc": "0.5%", "MemUsage": "20MiB / 1GiB"},
        ],
        project="ssce",
    )
    assert sample.cpu_pct == 2.5
    assert abs(sample.rss_mib - 120.0) < 0.2


def test_mqtt_connect_packet_starts_with_connect_type() -> None:
    packet = encode_connect("eval-client")
    assert packet[0] == 0x10
    assert b"MQTT" in packet
    assert b"eval-client" in packet


def test_cadence_median() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    published = [
        (start + timedelta(days=day * 10)).strftime("%Y-%m-%dT%H:%M:%SZ") for day in range(4)
    ]
    published.reverse()
    result = cadence_days(published)
    assert result["releases"] == 4
    assert result["median_days"] == 10.0


def test_login_form_parser() -> None:
    html = """
    <form action="/login" method="post">
      <input type="hidden" name="kc_csrf" value="abc">
      <input name="username" value="">
      <input type="password" name="password">
    </form>
    """
    parsed = parse_login_form(html, "https://auth.ss-control.test:8443/login")
    assert parsed is not None
    action, fields = parsed
    assert action.endswith("/login")
    assert "username" in fields
    assert "password" in fields


def test_kanidm_consent_token_input() -> None:
    from ss_control.eval.http_probe import _input_value

    html = '<form action="/ui/oauth2/consent"><input type="hidden" name="consent_token" value="tok-1"></form>'
    assert _input_value(html, "consent_token") == "tok-1"


def test_authelia_redirect_parser() -> None:
    from ss_control.eval.http_probe import _authelia_redirect

    assert (
        _authelia_redirect({"status": "OK", "data": {"redirect": "https://app.test/"}})
        == "https://app.test/"
    )


def test_audit_needles() -> None:
    ok = audit_from_logs({"keycloak": "type=LOGIN user=eval"}, ("type=LOGIN", "missing"))
    assert ok.passed
    bad = audit_from_logs({"caddy": "GET /health"}, ("type=LOGIN",))
    assert not bad.passed


def test_jwt_validator_from_jwks() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    import base64

    def b64(value: int, size: int) -> str:
        return base64.urlsafe_b64encode(value.to_bytes(size, "big")).rstrip(b"=").decode("ascii")

    jwk = {
        "keys": [
            {
                "kty": "RSA",
                "kid": "k1",
                "n": b64(numbers.n, 256),
                "e": b64(numbers.e, 3),
            }
        ]
    }
    token = jwt.encode(
        {
            "sub": "eval-operator",
            "iss": "https://auth.ss-control.test:8443/realms/ss",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        key,
        algorithm="RS256",
        headers={"kid": "k1"},
    )
    validator = validator_for_token(
        token, jwk, issuer="https://auth.ss-control.test:8443/realms/ss"
    )
    assert validator.decode(token)["sub"] == "eval-operator"


def test_caddyfile_switches_forward_auth() -> None:
    authelia = next(item for item in CANDIDATES if item.idp == "authelia")
    keycloak = next(item for item in CANDIDATES if item.idp == "keycloak")
    authelia_text = render_caddyfile(authelia)
    keycloak_text = render_caddyfile(keycloak)
    assert "authelia:9091" in authelia_text
    assert "/api/authz/forward-auth" in authelia_text
    assert "oauth2-proxy:4180" in keycloak_text
    assert "keycloak:8080" in keycloak_text
    assert ":18443" in keycloak_text
    assert "/etc/caddy/certs/caddy.crt" in keycloak_text


def test_sso_href_parser() -> None:
    from ss_control.eval.http_probe import _sso_href

    html = '<a href="/auth/strategy">Sign in with SSO</a>'
    assert _sso_href(html, "https://nodered.ss-control.test:18443/").endswith("/auth/strategy")


def test_grpc_web_http_urls() -> None:
    from ss_control.eval.probes_run import _grpc_web_frame, _grpc_web_http_urls, _proto_string

    url = "https://example.test/x"
    inner = _proto_string(1, url)
    frame = _grpc_web_frame(inner)
    assert _grpc_web_http_urls(frame) == [url]


def test_chirpstack_oidc_code_state_from_hash_route() -> None:
    from ss_control.eval.probes_run import oidc_code_state

    url = "https://chirpstack.ss-control.test:18443/#/login?code=abc.def&state=xyz"
    assert oidc_code_state(url) == ("abc.def", "xyz")


def test_oidc_urls_and_env_escape() -> None:
    assert "realms/ss" in oidc_urls("keycloak")["OIDC_ISSUER"]
    assert escape_env("ab$cd") == "ab$$cd"


def test_chirpstack_toml_selects_openid_connect_backend() -> None:
    from ss_control.eval.idp_files import chirpstack_toml

    text = chirpstack_toml(
        {
            "postgres_password": "pg",
            "client_secret": "secret",
            "chirpstack_api_secret": "api",
        },
        issuer="https://auth.ss-control.test:18443/realms/ss",
        token_hint="http://keycloak:8080/realms/ss/protocol/openid-connect/token",
    )
    assert 'enabled="openid_connect"' in text
    assert "registration_enabled=true" in text
    assert "provider_url=" in text
    assert "login_label=" in text


def test_authelia_jwk_block_is_indented() -> None:
    from ss_control.eval.idp_files import authelia_config, generate_rsa_private_pem

    pem = generate_rsa_private_pem().decode("utf-8")
    text = authelia_config(
        {
            "client_secret": "secret",
            "authelia_session_secret": "s" * 32,
            "authelia_storage_key": "k" * 32,
            "authelia_hmac_secret": "h" * 32,
            "authelia_jwt_secret": "j" * 32,
        },
        pem,
    )
    key_line = next(line for line in text.splitlines() if line.strip() == "- key: |")
    begin = next(line for line in text.splitlines() if "BEGIN PRIVATE KEY" in line)
    assert (len(begin) - len(begin.lstrip(" "))) > (len(key_line) - len(key_line.lstrip(" ")))
    assert "jwt_secret:" in text
    assert "grant_types: [client_credentials]" in text
    assert "scopes: [groups]" in text
    assert "token_endpoint_auth_method: client_secret_basic" in text
    assert "requested_audience_mode: implicit" in text


def test_kanidm_parse_password_from_noisy_json() -> None:
    from ss_control.eval.kanidm_setup import _parse_password

    blob = 'WARN tls\n{"new_credential": "CorrectHorse", "result": "ok"}\n'
    assert _parse_password(blob) == "CorrectHorse"


def test_kanidm_secret_from_json_and_text() -> None:
    from ss_control.eval.kanidm_setup import _secret_from_output

    assert _secret_from_output('{"secret": "s3cretValue"}') == "s3cretValue"
    text = "WARN tls disabled\nTheSecretValueHere\nSuccess\n"
    assert _secret_from_output(text) == "TheSecretValueHere"


def test_select_stack_picks_lightest_passing_composition() -> None:
    def _result(cid: str, rss: float, extra_fail: str | None = None) -> CandidateResult:
        probes = [
            ProbeResult("oidc_grafana", True),
            ProbeResult("oidc_chirpstack", True),
            ProbeResult("oidc_nodered", True),
            ProbeResult("forward_auth_streamlit", True),
            ProbeResult("forward_auth_frigate", True),
            ProbeResult("jwt_ss_kit_web", True),
            ProbeResult("mtls_accept", True),
            ProbeResult("mtls_reject", True),
            ProbeResult("audit_log", True),
            ProbeResult("registry_api", True),
            ProbeResult("fusion_incidents", True),
        ]
        if extra_fail:
            probes = [
                item if item.name != extra_fail else ProbeResult(extra_fail, False)
                for item in probes
            ]
        return CandidateResult(
            candidate_id=cid,
            idle=ResourceSample(0.1, rss / 2),
            peak=ResourceSample(1.0, rss),
            probes=probes,
        )

    decision = select_stack(
        [
            _result("keycloak-composition", 800),
            _result("authelia-composition", 250),
            _result("kanidm-composition", 400),
            CandidateResult("openremote-keycloak", error="timeout"),
        ]
    )
    assert decision["identity_provider"] == "authelia"
    assert decision["proxy"] == "caddy"
    assert decision["ca"] == "step-ca"
    assert decision["openremote"] == "replaced"

    fallback = select_stack(
        [
            _result("keycloak-composition", 800),
            _result("authelia-composition", 250, extra_fail="oidc_chirpstack"),
        ]
    )
    assert fallback["identity_provider"] == "keycloak"
