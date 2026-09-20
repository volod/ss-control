"""Unit tests for the production stack (no Docker)."""

from pathlib import Path

from ss_control.stack.models import PUBLIC_HOSTS
from ss_control.stack.paths import compose_file, project_root
from ss_control.stack.ports import only_ingress_ports, services_with_published_ports
from ss_control.stack.render import authelia_config, authelia_users
from ss_control.stack.secrets import generate_secrets, write_env_secrets


def test_compose_publishes_only_http_https() -> None:
    text = compose_file().read_text(encoding="utf-8")
    published = services_with_published_ports(text)
    assert published == {"caddy": [80, 443]}
    ok, detail = only_ingress_ports(text)
    assert ok, detail
    assert "ports:" in text
    for service in ("grafana", "prometheus", "cadvisor", "mosquitto", "authelia", "nodered"):
        assert service in text


def test_caddyfile_forward_auth_and_oidc_hosts() -> None:
    text = (project_root() / "config" / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    assert "forward_auth authelia:9091" in text
    assert "https://video.{$SS_CONTROL_DOMAIN}" in text
    assert "https://frigate.{$SS_CONTROL_DOMAIN}" in text
    assert "https://grafana.{$SS_CONTROL_DOMAIN}" in text
    assert "https://nodered.{$SS_CONTROL_DOMAIN}" in text
    assert "https://chirpstack.{$SS_CONTROL_DOMAIN}" in text
    assert "redir https://{host}{uri} permanent" in text
    assert "openremote" not in text.lower()


def test_mosquitto_requires_site_ca_client_cert() -> None:
    text = (project_root() / "config" / "mosquitto" / "mosquitto.conf").read_text(encoding="utf-8")
    assert "require_certificate true" in text
    assert "listener 8883" in text
    assert "allow_anonymous false" in text
    assert "listener 1883" not in text


def test_authelia_oidc_clients_and_admin_nodered() -> None:
    pem = "-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----"
    secrets = generate_secrets()
    text = authelia_config(secrets, pem, "ss-control.test")
    assert "client_id: grafana" in text
    assert "client_id: chirpstack" in text
    assert "client_id: nodered" in text
    assert "group:admins" in text
    assert "domain: nodered.ss-control.test" in text
    assert "https://grafana.ss-control.test/login/generic_oauth" in text
    assert "https://chirpstack.ss-control.test/auth/oidc/callback" in text
    assert "openremote" not in text.lower()
    users = authelia_users(secrets, "$pbkdf2-sha512$x")
    assert "admins" in users
    assert secrets["ADMIN_USER"] in users


def test_public_hosts_cover_operator_uis() -> None:
    assert "grafana" in PUBLIC_HOSTS
    assert "nodered" in PUBLIC_HOSTS
    assert "video" in PUBLIC_HOSTS
    assert "frigate" in PUBLIC_HOSTS
    assert "chirpstack" in PUBLIC_HOSTS


def test_secrets_file_mode_is_private(tmp_path: Path) -> None:
    path = tmp_path / ".env.secrets"
    write_env_secrets(path, generate_secrets())
    assert path.stat().st_mode & 0o777 == 0o600
    text = path.read_text(encoding="utf-8")
    assert "ADMIN_PASSWORD=" in text
    assert "STEP_CA_PASSWORD=" in text
    assert "OR_ADMIN" not in text


def test_hosts_snippet_lists_public_names() -> None:
    from ss_control.stack.render import hosts_snippet

    text = hosts_snippet("ss-control.test")
    assert text.startswith("127.0.0.1 ")
    assert "grafana.ss-control.test" in text
    assert "auth.ss-control.test" in text


def test_ensure_leaf_duration_sets_max(tmp_path: Path) -> None:
    from ss_control.stack.ca import ensure_leaf_duration

    ca_json = tmp_path / "config" / "ca.json"
    ca_json.parent.mkdir(parents=True)
    ca_json.write_text(
        '{"authority": {"provisioners": [{"type": "JWK", "name": "ss-control"}]}}\n',
        encoding="utf-8",
    )
    assert ensure_leaf_duration(tmp_path, "2160h") is True
    assert ensure_leaf_duration(tmp_path, "2160h") is False
    text = ca_json.read_text(encoding="utf-8")
    assert '"maxTLSCertDuration": "2160h"' in text
