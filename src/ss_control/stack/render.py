"""Render Authelia runtime config for the production stack."""

from pathlib import Path

from ss_control.eval.idp_files import generate_rsa_private_pem, write_bytes, write_text
from ss_control.stack.models import PUBLIC_HOSTS, public_url


def authelia_users(secrets: dict[str, str], password_hash: str) -> str:
    """File backend users.yml with the operator in the admins group."""
    return f"""\
users:
  {secrets["ADMIN_USER"]}:
    disabled: false
    displayname: Site Operator
    password: '{password_hash}'
    email: {secrets["ADMIN_EMAIL"]}
    groups:
      - admins
"""


def authelia_config(secrets: dict[str, str], jwk_pem: str, domain: str) -> str:
    """Authelia configuration: OIDC clients plus admin-only Node-RED."""
    origin = public_url("auth", domain)
    grafana = public_url("grafana", domain)
    chirpstack = public_url("chirpstack", domain)
    nodered = public_url("nodered", domain)
    grafana_secret = secrets["GRAFANA_CLIENT_SECRET"]
    chirpstack_secret = secrets["CHIRPSTACK_CLIENT_SECRET"]
    nodered_secret = secrets["NODERED_CLIENT_SECRET"]
    pem_indented = "\n".join(f"            {line}" for line in jwk_pem.strip().splitlines())
    return f"""\
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
    jwt_secret: {secrets["AUTHELIA_JWT_SECRET"]}
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
    - domain: auth.{domain}
      policy: bypass
    - domain: nodered.{domain}
      policy: one_factor
      subject:
        - "group:admins"
    - domain: prometheus.{domain}
      policy: one_factor
      subject:
        - "group:admins"
    - domain: "*.{domain}"
      policy: one_factor
session:
  secret: {secrets["AUTHELIA_SESSION_SECRET"]}
  cookies:
    - name: authelia_session
      domain: {domain}
      authelia_url: {origin}
      default_redirection_url: {grafana}
storage:
  encryption_key: {secrets["AUTHELIA_STORAGE_KEY"]}
  local:
    path: /config/db.sqlite3
notifier:
  filesystem:
    filename: /config/notification.txt
identity_providers:
  oidc:
    hmac_secret: {secrets["AUTHELIA_HMAC_SECRET"]}
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
        client_secret: '$plaintext${grafana_secret}'
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
        client_secret: '$plaintext${chirpstack_secret}'
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
        client_secret: '$plaintext${nodered_secret}'
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
"""


def write_authelia_runtime(
    authelia_dir: Path,
    secrets: dict[str, str],
    *,
    password_hash: str,
    domain: str,
) -> Path:
    """Write configuration.yml, users.yml, and a persistent OIDC JWK."""
    authelia_dir.mkdir(parents=True, exist_ok=True)
    authelia_dir.chmod(0o777)
    jwk_path = authelia_dir / "oidc-jwk.pem"
    if jwk_path.is_file():
        pem = jwk_path.read_bytes()
    else:
        pem = generate_rsa_private_pem()
        write_bytes(jwk_path, pem)
        jwk_path.chmod(0o600)
    write_text(
        authelia_dir / "configuration.yml",
        authelia_config(secrets, pem.decode("utf-8"), domain),
    )
    write_text(authelia_dir / "users.yml", authelia_users(secrets, password_hash))
    return jwk_path


def hosts_snippet(domain: str) -> str:
    """One /etc/hosts line sending every public name to loopback."""
    names = [domain, *[f"{name}.{domain}" for name in PUBLIC_HOSTS]]
    return "127.0.0.1 " + " ".join(names) + "\n"


def write_hosts_snippet(path: Path, domain: str) -> None:
    """Write a hosts snippet operators can append with sudo."""
    write_text(path, hosts_snippet(domain))
