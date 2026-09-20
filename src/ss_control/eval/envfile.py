"""Write docker compose .env files without leaking interpolation."""

from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlencode

from ss_control.eval.models import (
    CADDY_LISTEN_HTTP,
    CADDY_LISTEN_HTTPS,
    EVAL_DOMAIN,
    IMAGES,
    MQTT_TLS_PORT,
    OPENREMOTE_HTTPS_PORT,
    PROXY_HTTP_PORT,
    PROXY_HTTPS_PORT,
    public_host,
    public_url,
)


def escape_env(value: str) -> str:
    """Escape `$` so Compose does not interpolate secrets."""
    return value.replace("\\", "\\\\").replace("$", "$$").replace("\n", "")


def oidc_urls(idp: str) -> dict[str, str]:
    """Public and in-cluster OIDC endpoints for an identity provider."""
    public_issuer_kc = f"{public_url('auth')}/realms/ss"
    if idp == "keycloak":
        return {
            "OIDC_ISSUER": public_issuer_kc,
            "OIDC_PUBLIC_ORIGIN": public_url("auth"),
            "OIDC_AUTH_URL": f"{public_issuer_kc}/protocol/openid-connect/auth",
            "OIDC_TOKEN_URL": "http://keycloak:8080/realms/ss/protocol/openid-connect/token",
            "OIDC_USERINFO_URL": "http://keycloak:8080/realms/ss/protocol/openid-connect/userinfo",
            "OIDC_JWKS_URL": f"{public_issuer_kc}/protocol/openid-connect/certs",
            "OIDC_TOKEN_PUBLIC": f"{public_issuer_kc}/protocol/openid-connect/token",
            "CHIRPSTACK_PROVIDER": public_issuer_kc,
            "NODERED_OIDC_ISSUER": public_issuer_kc,
            "OAUTH2_OIDC_ISSUER": public_issuer_kc,
            "OAUTH2_ISSUER_INTERNAL": "http://keycloak:8080/realms/ss",
        }
    if idp == "authelia":
        origin = public_url("auth")
        return {
            "OIDC_ISSUER": origin,
            "OIDC_PUBLIC_ORIGIN": origin,
            "OIDC_AUTH_URL": f"{origin}/api/oidc/authorization",
            "OIDC_TOKEN_URL": "http://authelia:9091/api/oidc/token",
            "OIDC_USERINFO_URL": "http://authelia:9091/api/oidc/userinfo",
            "OIDC_JWKS_URL": f"{origin}/jwks.json",
            "OIDC_TOKEN_PUBLIC": f"{origin}/api/oidc/token",
            "CHIRPSTACK_PROVIDER": origin,
            "NODERED_OIDC_ISSUER": origin,
            "OAUTH2_OIDC_ISSUER": origin,
            "OAUTH2_ISSUER_INTERNAL": "http://authelia:9091",
        }
    origin = public_url("auth")
    issuer = f"{origin}/oauth2/openid/grafana"
    return {
        "OIDC_ISSUER": issuer,
        "OIDC_PUBLIC_ORIGIN": origin,
        "OIDC_AUTH_URL": f"{origin}/ui/oauth2",
        "OIDC_TOKEN_URL": f"{origin}/oauth2/token",
        "OIDC_USERINFO_URL": f"{issuer}/userinfo",
        "OIDC_JWKS_URL": f"{issuer}/public_key.jwk",
        "OIDC_TOKEN_PUBLIC": f"{origin}/oauth2/token",
        "CHIRPSTACK_PROVIDER": f"{origin}/oauth2/openid/chirpstack",
        "NODERED_OIDC_ISSUER": f"{origin}/oauth2/openid/nodered",
        "OAUTH2_OIDC_ISSUER": f"{origin}/oauth2/openid/oauth2-proxy",
        "OAUTH2_ISSUER_INTERNAL": "https://kanidm:8443/oauth2/openid/oauth2-proxy",
    }


def authorize_url(idp: str, client_id: str, redirect_uri: str) -> str:
    """Build an OIDC authorization request for a confidential client."""
    urls = oidc_urls(idp)
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid profile email",
        }
    )
    return f"{urls['OIDC_AUTH_URL']}?{query}"


def compose_env(
    *,
    project: str,
    config_dir: Path,
    data_dir: Path,
    eval_root: Path,
    secrets: Mapping[str, str],
    idp: str,
) -> dict[str, str]:
    """Environment for docker compose variable substitution."""
    urls = oidc_urls(idp)
    env = {
        "COMPOSE_PROJECT": project,
        "EVAL_DOMAIN": EVAL_DOMAIN,
        "PROXY_HTTPS_PORT": str(PROXY_HTTPS_PORT),
        "PROXY_HTTP_PORT": str(PROXY_HTTP_PORT),
        "CADDY_LISTEN_HTTPS": str(CADDY_LISTEN_HTTPS),
        "CADDY_LISTEN_HTTP": str(CADDY_LISTEN_HTTP),
        "MQTT_TLS_PORT": str(MQTT_TLS_PORT),
        "OPENREMOTE_HTTPS_PORT": str(OPENREMOTE_HTTPS_PORT),
        "EVAL_CONFIG_DIR": str(config_dir),
        "EVAL_DATA_DIR": str(data_dir),
        "EVAL_STUB_CONTEXT": str(eval_root / "eval" / "stubs"),
        "EVAL_NODERED_CONTEXT": str(eval_root / "eval" / "nodered"),
        "EVAL_MOSQUITTO_CONF": str(eval_root / "eval" / "mosquitto" / "mosquitto.conf"),
        "EVAL_CHIRPSTACK_REGION": str(eval_root / "eval" / "chirpstack" / "region_eu868.toml"),
        "EVAL_CHIRPSTACK_ENTRYPOINT": str(eval_root / "eval" / "chirpstack" / "entrypoint.sh"),
        "EVAL_AUTHELIA_DIR": str(data_dir / "authelia"),
        "EVAL_NODERED_SETTINGS": str(eval_root / "eval" / "nodered" / "settings.js"),
        "CADDY_IMAGE": IMAGES["caddy"],
        "KEYCLOAK_IMAGE": IMAGES["keycloak"],
        "AUTHELIA_IMAGE": IMAGES["authelia"],
        "KANIDM_IMAGE": IMAGES["kanidm"],
        "STEP_CA_IMAGE": IMAGES["step_ca"],
        "GRAFANA_IMAGE": IMAGES["grafana"],
        "CHIRPSTACK_IMAGE": IMAGES["chirpstack"],
        "MOSQUITTO_IMAGE": IMAGES["mosquitto"],
        "POSTGRES_IMAGE": IMAGES["postgres"],
        "REDIS_IMAGE": IMAGES["redis"],
        "OAUTH2_PROXY_IMAGE": IMAGES["oauth2_proxy"],
        "OPENREMOTE_PROXY_IMAGE": IMAGES["openremote_proxy"],
        "OPENREMOTE_KEYCLOAK_IMAGE": IMAGES["openremote_keycloak"],
        "OPENREMOTE_MANAGER_IMAGE": IMAGES["openremote_manager"],
        "OPENREMOTE_POSTGRES_IMAGE": IMAGES["openremote_postgres"],
        "ADMIN_USER": secrets["admin_user"],
        "ADMIN_PASSWORD": secrets["admin_password"],
        "POSTGRES_PASSWORD": secrets["postgres_password"],
        "KEYCLOAK_ADMIN_PASSWORD": secrets["keycloak_admin_password"],
        "CLIENT_SECRET": secrets["client_secret"],
        "GRAFANA_CLIENT_SECRET": secrets.get("grafana_client_secret") or secrets["client_secret"],
        "NODERED_CLIENT_SECRET": secrets.get("nodered_client_secret") or secrets["client_secret"],
        "CHIRPSTACK_CLIENT_SECRET": secrets.get("chirpstack_client_secret")
        or secrets["client_secret"],
        "OAUTH2_CLIENT_SECRET": secrets.get("oauth2_client_secret") or secrets["client_secret"],
        "OAUTH2_COOKIE_SECRET": secrets["oauth2_cookie_secret"],
        "STEP_CA_PASSWORD": secrets["step_ca_password"],
        "STEP_PROVISIONER": secrets["step_provisioner"],
        "NODERED_CREDENTIAL_SECRET": secrets["nodered_credential_secret"],
        "OPENREMOTE_ADMIN_PASSWORD": secrets["openremote_admin_password"],
        "GRAFANA_ROOT_URL": public_url("grafana"),
        "NODERED_CALLBACK_URL": f"{public_url('nodered')}/auth/strategy/callback",
        "OR_HOSTNAME": public_host("auth"),
        **urls,
    }
    return env


def write_env_file(path: Path, env: Mapping[str, str]) -> None:
    """Write KEY=value lines for Compose `--env-file`."""
    lines = [f"{key}={escape_env(value)}" for key, value in sorted(env.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
