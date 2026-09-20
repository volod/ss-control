"""Validate an OIDC access token with `ss_kit.web.jwt`."""

import json
from typing import Any
from urllib.parse import urljoin

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from jwt.algorithms import ECAlgorithm, RSAAlgorithm
from ss_kit.web.jwt import JwtConfig, JwtValidator

from ss_control.eval.models import ProbeResult


def _pem_from_jwk(jwk: dict[str, Any]) -> bytes:
    kty = jwk.get("kty")
    if kty == "RSA":
        key = RSAAlgorithm.from_jwk(json.dumps(jwk))
    elif kty == "EC":
        key = ECAlgorithm.from_jwk(json.dumps(jwk))
    else:
        raise ValueError(f"unsupported JWK kty {kty!r}")
    return key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def fetch_jwks(client: httpx.Client, jwks_url: str) -> dict[str, Any]:
    """GET a JWKS document."""
    response = client.get(jwks_url)
    response.raise_for_status()
    return response.json()


def validator_for_token(
    token: str,
    jwks: dict[str, Any],
    *,
    issuer: str | None,
    audience: str | list[str] | None = None,
) -> JwtValidator:
    """Build a `JwtValidator` from the JWKS key that matches `kid`."""
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    alg = header.get("alg") or "RS256"
    keys = jwks.get("keys") or []
    chosen = None
    for key in keys:
        if kid and key.get("kid") == kid:
            chosen = key
            break
    if chosen is None and keys:
        chosen = keys[0]
    if chosen is None:
        raise ValueError("JWKS document has no keys")
    pem = _pem_from_jwk(chosen)
    return JwtValidator(JwtConfig(key=pem, algorithms=(alg,), issuer=issuer, audience=audience))


def client_credentials_token(
    client: httpx.Client,
    token_url: str,
    *,
    client_id: str,
    client_secret: str,
    scope: str = "openid",
    extra: dict[str, str] | None = None,
) -> str:
    """Resource-owner-independent access token."""
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope,
    }
    if extra:
        data.update(extra)
    response = client.post(
        token_url,
        data=data,
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise ValueError("token response had no access_token")
    return str(token)


def password_token(
    client: httpx.Client,
    token_url: str,
    *,
    client_id: str,
    client_secret: str,
    username: str,
    password: str,
    scope: str = "openid profile email",
) -> str:
    """Resource-owner password grant when the IdP allows it."""
    response = client.post(
        token_url,
        data={
            "grant_type": "password",
            "client_id": client_id,
            "client_secret": client_secret,
            "username": username,
            "password": password,
            "scope": scope,
        },
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise ValueError("token response had no access_token")
    return str(token)


def probe_jwt(
    client: httpx.Client,
    *,
    issuer: str,
    token_url: str,
    jwks_url: str | None = None,
    client_id: str,
    client_secret: str,
    username: str = "",
    password: str = "",
    scope: str = "openid",
    extra: dict[str, str] | None = None,
) -> ProbeResult:
    """Obtain a token and decode it with `ss_kit.web.jwt.JwtValidator`."""
    jwks_url = jwks_url or urljoin(issuer.rstrip("/") + "/", "protocol/openid-connect/certs")
    try:
        try:
            token = client_credentials_token(
                client,
                token_url,
                client_id=client_id,
                client_secret=client_secret,
                scope=scope,
                extra=extra,
            )
            source = "client_credentials"
        except (httpx.HTTPError, ValueError):
            if not username:
                raise
            token = password_token(
                client,
                token_url,
                client_id=client_id,
                client_secret=client_secret,
                username=username,
                password=password,
            )
            source = "password"
        jwks = fetch_jwks(client, jwks_url)
        unverified = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
        audience = unverified.get("aud") or None
        if isinstance(audience, list) and not audience:
            audience = None
        try:
            validator = validator_for_token(token, jwks, issuer=issuer, audience=audience)
            claims = validator.decode(token)
        except jwt.MissingRequiredClaimError:
            validator = validator_for_token(token, jwks, issuer=issuer, audience=None)
            claims = validator.decode(token)
    except (httpx.HTTPError, ValueError, jwt.InvalidTokenError, KeyError) as exc:
        return ProbeResult("jwt_ss_kit_web", False, f"{type(exc).__name__}: {exc}")
    subject = claims.get("sub") or claims.get("preferred_username") or ""
    return ProbeResult("jwt_ss_kit_web", True, f"{source} sub={subject}")
