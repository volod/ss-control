"""Render identity-provider and app config files for one candidate."""

import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ss_control.eval.models import Candidate, public_url


def postgres_init_sql(secrets: dict[str, str]) -> str:
    password = secrets["postgres_password"]
    return f"""
CREATE USER keycloak WITH PASSWORD '{password}';
CREATE DATABASE keycloak OWNER keycloak;
CREATE USER chirpstack WITH PASSWORD '{password}';
CREATE DATABASE chirpstack OWNER chirpstack;
\\c chirpstack
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gist;
""".lstrip()


_GROUPS_MAPPER = {
    "name": "groups",
    "protocol": "openid-connect",
    "protocolMapper": "oidc-group-membership-mapper",
    "consentRequired": False,
    "config": {
        "full.path": "false",
        "id.token.claim": "true",
        "access.token.claim": "true",
        "userinfo.token.claim": "true",
        "claim.name": "groups",
    },
}


def keycloak_realm(secrets: dict[str, str]) -> dict[str, Any]:
    secret = secrets["client_secret"]
    redirects = {
        "grafana": f"{public_url('grafana')}/login/generic_oauth",
        "chirpstack": f"{public_url('chirpstack')}/auth/oidc/callback",
        "nodered": f"{public_url('nodered')}/auth/strategy",
        "oauth2-proxy": f"{public_url('streamlit')}/oauth2/callback",
        "eval-cli": f"{public_url('fusion')}/",
    }
    clients = []
    for client_id, redirect in redirects.items():
        clients.append(
            {
                "clientId": client_id,
                "enabled": True,
                "protocol": "openid-connect",
                "publicClient": False,
                "secret": secret,
                "redirectUris": [
                    redirect,
                    f"{public_url('nodered')}/auth/strategy/callback",
                    f"{public_url('frigate')}/oauth2/callback",
                    f"{public_url('streamlit')}/oauth2/callback",
                ],
                "webOrigins": ["+"],
                "standardFlowEnabled": True,
                "directAccessGrantsEnabled": True,
                "serviceAccountsEnabled": client_id in {"eval-cli", "oauth2-proxy"},
                "fullScopeAllowed": True,
                "defaultClientScopes": ["web-origins", "acr", "profile", "roles", "email", "basic"],
                "optionalClientScopes": ["address", "phone", "offline_access", "microprofile-jwt"],
                "protocolMappers": [_GROUPS_MAPPER],
            }
        )
    return {
        "realm": "ss",
        "enabled": True,
        "sslRequired": "none",
        "registrationAllowed": False,
        "loginWithEmailAllowed": True,
        "eventsEnabled": True,
        "eventsListeners": ["jboss-logging"],
        "adminEventsEnabled": True,
        "adminEventsDetailsEnabled": True,
        "users": [
            {
                "username": secrets["admin_user"],
                "enabled": True,
                "email": secrets["admin_email"],
                "emailVerified": True,
                "firstName": "Eval",
                "lastName": "Operator",
                "credentials": [
                    {"type": "password", "value": secrets["admin_password"], "temporary": False}
                ],
                "groups": ["admins"],
            }
        ],
        "groups": [{"name": "admins"}],
        "clients": clients,
    }


def chirpstack_toml(secrets: dict[str, str], *, issuer: str, token_hint: str) -> str:
    password = secrets["postgres_password"]
    client_secret = secrets.get("chirpstack_client_secret") or secrets["client_secret"]
    return f"""
[postgresql]
dsn="postgres://chirpstack:{password}@postgres/chirpstack?sslmode=disable"

[redis]
servers=["redis://redis:6379"]

[api]
bind="0.0.0.0:8080"
secret={secrets["chirpstack_api_secret"]!r}

[gateway]
  [gateway.backend]
    enabled=["mqtt"]
    [gateway.backend.mqtt]
      server="tcp://mosquitto:1883"

[network]
net_id="000000"
enabled_regions=["eu868"]

[user_authentication]
enabled="openid_connect"

  [user_authentication.openid_connect]
    registration_enabled=true
    provider_url="{issuer}"
    client_id="chirpstack"
    client_secret={client_secret!r}
    redirect_url="{public_url("chirpstack")}/auth/oidc/callback"
    login_redirect=true
    login_label="SSO"
    assume_email_verified=true
    scopes=["openid", "email", "profile"]
    # token_hint={token_hint}
""".lstrip()


def authelia_users(secrets: dict[str, str], password_hash: str) -> str:
    return f"""
users:
  {secrets["admin_user"]}:
    disabled: false
    displayname: Eval Operator
    password: '{password_hash}'
    email: {secrets["admin_email"]}
    groups:
      - admins
""".lstrip()


def authelia_config(secrets: dict[str, str], jwk_pem: str) -> str:
    origin = public_url("auth")
    grafana = public_url("grafana")
    chirpstack = public_url("chirpstack")
    nodered = public_url("nodered")
    streamlit = public_url("streamlit")
    frigate = public_url("frigate")
    secret = secrets["client_secret"]
    pem_indented = "\n".join(f"            {line}" for line in jwk_pem.strip().splitlines())
    return f"""
theme: light
server:
  address: tcp://0.0.0.0:9091
  endpoints:
    authz:
      forward-auth:
        implementation: ForwardAuth
log:
  level: info
identity_validation:
  reset_password:
    jwt_secret: {secrets["authelia_jwt_secret"]}
authentication_backend:
  file:
    path: /config/users.yml
totp:
  disable: true
webauthn:
  disable: true
access_control:
  default_policy: deny
  rules:
    - domain: auth.ss-control.test
      policy: bypass
    - domain: "*.ss-control.test"
      policy: one_factor
session:
  secret: {secrets["authelia_session_secret"]}
  cookies:
    - name: authelia_session
      domain: ss-control.test
      authelia_url: {origin}
      default_redirection_url: {grafana}
storage:
  encryption_key: {secrets["authelia_storage_key"]}
  local:
    path: /config/db.sqlite3
notifier:
  filesystem:
    filename: /config/notification.txt
identity_providers:
  oidc:
    hmac_secret: {secrets["authelia_hmac_secret"]}
    jwks:
      - key: |
{pem_indented}
    cors:
      endpoints:
        - authorization
        - token
        - revocation
        - introspection
        - userinfo
      allowed_origins_from_client_redirect_uris: true
    clients:
      - client_id: grafana
        client_name: Grafana
        client_secret: '$plaintext${secret}'
        public: false
        authorization_policy: one_factor
        consent_mode: implicit
        require_pkce: false
        redirect_uris:
          - {grafana}/login/generic_oauth
        scopes: [openid, profile, email, groups]
        grant_types: [authorization_code]
        response_types: [code]
        token_endpoint_auth_method: client_secret_post
      - client_id: chirpstack
        client_name: ChirpStack
        client_secret: '$plaintext${secret}'
        public: false
        authorization_policy: one_factor
        consent_mode: implicit
        require_pkce: false
        redirect_uris:
          - {chirpstack}/auth/oidc/callback
        scopes: [openid, profile, email, groups]
        grant_types: [authorization_code]
        token_endpoint_auth_method: client_secret_basic
      - client_id: nodered
        client_name: Node-RED
        client_secret: '$plaintext${secret}'
        public: false
        authorization_policy: one_factor
        consent_mode: implicit
        require_pkce: false
        redirect_uris:
          - {nodered}/auth/strategy
          - {nodered}/auth/strategy/callback
        scopes: [openid, profile, email, groups]
        grant_types: [authorization_code]
        token_endpoint_auth_method: client_secret_post
      - client_id: eval-cli
        client_name: eval-cli
        client_secret: '$plaintext${secret}'
        public: false
        authorization_policy: one_factor
        consent_mode: implicit
        redirect_uris: []
        scopes: [groups]
        grant_types: [client_credentials]
        token_endpoint_auth_method: client_secret_post
        access_token_signed_response_alg: RS256
        requested_audience_mode: implicit
        audience:
          - eval-cli
      - client_id: oauth2-proxy
        client_name: oauth2-proxy
        client_secret: '$plaintext${secret}'
        public: false
        authorization_policy: one_factor
        consent_mode: implicit
        redirect_uris:
          - {streamlit}/oauth2/callback
          - {frigate}/oauth2/callback
        scopes: [openid, profile, email, groups]
        grant_types: [authorization_code]
        token_endpoint_auth_method: client_secret_basic
""".lstrip()


def generate_rsa_private_pem() -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def kanidm_server_toml() -> str:
    origin = public_url("auth")
    return f"""
bindaddress = "[::]:8443"
db_path = "/data/kanidm.db"
tls_chain = "/data/server.pem"
tls_key = "/data/server.key"
domain = "auth.ss-control.test"
origin = "{origin}"
log_level = "info"
""".lstrip()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def render_candidate_configs(
    config_dir: Path,
    candidate: Candidate,
    secrets: dict[str, str],
    *,
    issuer: str,
    token_url: str,
    authelia_password_hash: str = "",
) -> None:
    """Write generated config files for one candidate into config_dir."""
    write_text(config_dir / "postgres-init.sql", postgres_init_sql(secrets))
    write_text(
        config_dir / "chirpstack.toml",
        chirpstack_toml(secrets, issuer=issuer, token_hint=token_url),
    )
    if candidate.idp == "keycloak":
        write_text(config_dir / "realm.json", json.dumps(keycloak_realm(secrets), indent=2) + "\n")
    if candidate.idp == "authelia":
        pem = generate_rsa_private_pem()
        write_bytes(config_dir / "authelia-jwk.pem", pem)
        write_text(config_dir / "authelia.yml", authelia_config(secrets, pem.decode("utf-8")))
        write_text(
            config_dir / "authelia-users.yml", authelia_users(secrets, authelia_password_hash)
        )
        authelia_dir = config_dir.parent / "data" / "authelia"
        authelia_dir.mkdir(parents=True, exist_ok=True)
        authelia_dir.chmod(0o777)
        write_text(authelia_dir / "configuration.yml", (config_dir / "authelia.yml").read_text())
        write_text(authelia_dir / "users.yml", (config_dir / "authelia-users.yml").read_text())
        write_bytes(authelia_dir / "oidc-jwk.pem", pem)
    if candidate.idp == "kanidm":
        write_text(config_dir / "kanidm-server.toml", kanidm_server_toml())
