"""Write Caddyfiles for each identity provider."""

from ss_control.eval.models import CADDY_LISTEN_HTTPS, EVAL_DOMAIN, Candidate, public_host


def _site(host: str, backend: str, extra: str = "") -> str:
    lines = [
        f"https://{host}:{CADDY_LISTEN_HTTPS} {{",
        "  tls /etc/caddy/certs/caddy.crt /etc/caddy/certs/caddy.key",
    ]
    if extra:
        lines.extend(f"  {line}" for line in extra.strip().splitlines())
    lines.append(f"  reverse_proxy {backend}")
    lines.append("}")
    return "\n".join(lines)


def _tls_backend(url: str) -> str:
    return "\n".join(
        [
            f"  reverse_proxy {url} {{",
            "    header_up Host {host}",
            "    header_up X-Forwarded-Proto {scheme}",
            "    transport http {",
            "      tls_insecure_skip_verify",
            "    }",
            "  }",
        ]
    )


def _forward_oauth2(host: str, backend: str) -> str:
    return f"""https://{host}:{CADDY_LISTEN_HTTPS} {{
  tls /etc/caddy/certs/caddy.crt /etc/caddy/certs/caddy.key
  handle /oauth2/* {{
    reverse_proxy oauth2-proxy:4180
  }}
  handle {{
    forward_auth oauth2-proxy:4180 {{
      uri /oauth2/auth
      copy_headers X-Auth-Request-User X-Auth-Request-Email X-Auth-Request-Groups
    }}
    reverse_proxy {backend}
  }}
}}"""


def _forward_authelia(host: str, backend: str) -> str:
    extra = """
forward_auth authelia:9091 {
    uri /api/authz/forward-auth
    copy_headers Remote-User Remote-Groups Remote-Email Remote-Name
}
"""
    return _site(host, backend, extra)


def render_caddyfile(candidate: Candidate) -> str:
    """Caddyfile: host-based ingress; listen port equals the public HTTPS port."""
    grafana = public_host("grafana")
    chirpstack = public_host("chirpstack")
    nodered = public_host("nodered")
    streamlit = public_host("streamlit")
    frigate = public_host("frigate")
    fusion = public_host("fusion")
    registry = public_host("registry")
    auth = public_host("auth")
    blocks = [
        "{",
        "  admin :2019",
        "  auto_https disable_redirects",
        f"  https_port {CADDY_LISTEN_HTTPS}",
        "  http_port 80",
        "}",
        "",
        _site(grafana, "grafana:3000"),
        _site(chirpstack, "chirpstack:8080"),
        _site(nodered, "nodered:1880"),
        _site(fusion, "stub:8080"),
        _site(registry, "stub:8080"),
    ]
    if candidate.idp == "authelia":
        blocks.append(_forward_authelia(streamlit, "stub:8080"))
        blocks.append(_forward_authelia(frigate, "stub:8080"))
        blocks.append(_site(auth, "authelia:9091"))
        blocks.append(f"http://{auth} {{\n  reverse_proxy authelia:9091\n}}")
    elif candidate.idp == "kanidm":
        blocks.append(_forward_oauth2(streamlit, "stub:8080"))
        blocks.append(_forward_oauth2(frigate, "stub:8080"))
        https_auth = "\n".join(
            [
                f"https://{auth}:{CADDY_LISTEN_HTTPS} {{",
                "  tls /etc/caddy/certs/caddy.crt /etc/caddy/certs/caddy.key",
                _tls_backend("https://kanidm:8443"),
                "}",
            ]
        )
        http_auth = "\n".join(
            [
                f"http://{auth} {{",
                _tls_backend("https://kanidm:8443"),
                "}",
            ]
        )
        blocks.append(https_auth)
        blocks.append(http_auth)
    else:
        blocks.append(_forward_oauth2(streamlit, "stub:8080"))
        blocks.append(_forward_oauth2(frigate, "stub:8080"))
        blocks.append(_site(auth, "keycloak:8080"))
        blocks.append(f"http://{auth} {{\n  reverse_proxy keycloak:8080\n}}")
    _ = EVAL_DOMAIN
    return "\n\n".join(blocks) + "\n"
