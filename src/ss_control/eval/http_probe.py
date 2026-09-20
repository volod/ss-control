"""HTTP login, forward-auth, and audit-log probes."""

import re
from collections.abc import Mapping
from html import unescape
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from ss_control.eval.models import ProbeResult

_FORM = re.compile(r"<form\b([^>]*)>(.*?)</form>", re.IGNORECASE | re.DOTALL)
_ACTION = re.compile(r'action=["\']([^"\']+)["\']', re.IGNORECASE)
_INPUT = re.compile(
    r"<input\b([^>]*?)>",
    re.IGNORECASE | re.DOTALL,
)
_ATTR = re.compile(r'([a-zA-Z0-9_-]+)\s*=\s*["\']([^"\']*)["\']')
_USER_FIELDS = ("username", "user", "email", "identifier")
_PASS_FIELDS = ("password", "pass")
_SSO_HREF = re.compile(
    r"""href=["']([^"']*(?:oauth|sso|oidc|strategy|generic_oauth|auth/oidc|/oauth2/start)[^"']*)["']""",
    re.IGNORECASE,
)
_LOGIN_MARKERS = ("sign in with", "sign in to", "openidconnect", "kc-form-login")


def _attrs(blob: str) -> dict[str, str]:
    return {match.group(1).lower(): unescape(match.group(2)) for match in _ATTR.finditer(blob)}


def parse_login_form(html: str, base_url: str) -> tuple[str, dict[str, str]] | None:
    """Return (action_url, default_fields) for the first password form."""
    for form_match in _FORM.finditer(html):
        body = form_match.group(2)
        fields: dict[str, str] = {}
        has_password = False
        for input_match in _INPUT.finditer(body + form_match.group(1)):
            attrs = _attrs(input_match.group(1))
            name = attrs.get("name")
            if not name:
                continue
            fields[name] = attrs.get("value", "")
            input_type = attrs.get("type", "text").lower()
            if input_type == "password":
                has_password = True
        if not has_password:
            continue
        action_match = _ACTION.search(form_match.group(1))
        action = unescape(action_match.group(1)) if action_match else ""
        action_url = urljoin(base_url, action or base_url)
        return action_url, fields
    return None


def _fill_credentials(fields: dict[str, str], username: str, password: str) -> dict[str, str]:
    filled = dict(fields)
    user_key = next((key for key in filled if key.lower() in _USER_FIELDS), None)
    pass_key = next((key for key in filled if key.lower() in _PASS_FIELDS), None)
    if user_key is None:
        user_key = next((key for key in filled if "user" in key.lower()), "username")
        filled.setdefault(user_key, "")
    if pass_key is None:
        pass_key = "password"
        filled.setdefault(pass_key, "")
    filled[user_key] = username
    filled[pass_key] = password
    return filled


def _sso_href(html: str, base_url: str) -> str | None:
    match = _SSO_HREF.search(html)
    if match is None:
        return None
    return urljoin(base_url, unescape(match.group(1)))


def _looks_like_login_page(html: str, base_url: str) -> bool:
    body = html.lower()
    if parse_login_form(html, base_url) is not None:
        return True
    return any(marker in body for marker in _LOGIN_MARKERS)


def _authelia_redirect(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data")
    if isinstance(data, dict) and data.get("redirect"):
        return str(data["redirect"])
    if payload.get("redirect"):
        return str(payload["redirect"])
    return ""


def authelia_first_factor(
    client: httpx.Client, page_url: str, username: str, password: str
) -> str | None:
    """POST Authelia's JSON first-factor API. Return the next URL or None."""
    parsed = urlparse(page_url)
    query = parse_qs(parsed.query)
    flow_id = (query.get("flow_id") or [""])[0]
    flow = (query.get("flow") or [""])[0]
    rd = (query.get("rd") or [""])[0]
    rm = (query.get("rm") or ["GET"])[0]
    if not flow_id and not rd:
        return None
    origin = f"{parsed.scheme}://{parsed.netloc}"
    body: dict[str, object] = {
        "username": username,
        "password": password,
        "keepMeLoggedIn": False,
    }
    if flow_id:
        body["flowID"] = flow_id
        body["flow"] = flow or "openid_connect"
    if rd:
        body["targetURL"] = rd
        body["requestMethod"] = rm
    try:
        response = client.post(f"{origin}/api/firstfactor", json=body)
    except httpx.HTTPError:
        return None
    if response.status_code >= 400:
        return None
    redirect = ""
    try:
        redirect = _authelia_redirect(response.json())
    except ValueError:
        redirect = ""
    location = response.headers.get("Location") or ""
    nxt = redirect or location
    if not nxt:
        return None
    return urljoin(origin + "/", nxt)


def _input_value(html: str, name: str) -> str:
    for input_match in _INPUT.finditer(html):
        attrs = _attrs(input_match.group(1))
        if attrs.get("name") == name:
            return attrs.get("value", "")
    return ""


def kanidm_password_login(
    client: httpx.Client, page_url: str, username: str, password: str
) -> str | None:
    """Complete Kanidm HTMX login, consent, and return the downstream URL."""
    parsed = urlparse(page_url)
    if "/ui/" not in parsed.path:
        return None
    origin = f"{parsed.scheme}://{parsed.netloc}"
    try:
        begin = client.post(
            f"{origin}/ui/login/begin",
            data={"username": username, "password": password},
        )
        if begin.status_code >= 400:
            return None
        landed = str(begin.url)
        body = begin.text
        if "/ui/login" in urlparse(landed).path or parse_login_form(body, landed):
            pw_page = client.post(f"{origin}/ui/login/pw", data={"password": password})
            if pw_page.status_code >= 400:
                return None
            landed = str(pw_page.url)
            body = pw_page.text
        if "/ui/login" in urlparse(landed).path:
            return None
        token = _input_value(body, "consent_token")
        if token:
            permit = client.post(f"{origin}/ui/oauth2/consent", data={"consent_token": token})
            if permit.status_code >= 400:
                return None
            landed = str(permit.url)
            body = permit.text
        if "/ui/" in urlparse(landed).path:
            replay = client.get(page_url)
            if replay.status_code >= 400:
                return None
            landed = str(replay.url)
            body = replay.text
            token = _input_value(body, "consent_token")
            if token:
                permit = client.post(f"{origin}/ui/oauth2/consent", data={"consent_token": token})
                if permit.status_code >= 400:
                    return None
                landed = str(permit.url)
        return landed
    except httpx.HTTPError:
        return None


def follow_login(
    client: httpx.Client,
    start_url: str,
    *,
    username: str,
    password: str,
    success_needles: tuple[str, ...] = (),
    success_host: str = "",
) -> ProbeResult:
    """Follow SSO redirects and password forms until the app or a failure."""
    name = start_url
    url = start_url
    last_detail = "not attempted"
    kanidm_tried = False
    try:
        for hop in range(8):
            page = client.get(url)
            last_detail = f"hop={hop} status={page.status_code} url={page.url}"
            if page.status_code == 401:
                parsed = urlparse(str(page.url) if page.url else url)
                url = f"{parsed.scheme}://{parsed.netloc}/oauth2/start"
                last_detail = f"401 -> {url}"
                continue
            if page.status_code >= 400:
                return ProbeResult(name, False, last_detail)
            if "error=" in str(page.url).lower() or "session_message=" in str(page.url).lower():
                return ProbeResult(name, False, f"idp error at {page.url}")
            html = page.text
            current = str(page.url)
            if "/ui/" in urlparse(current).path and not kanidm_tried:
                kanidm_tried = True
                kanidm_next = kanidm_password_login(client, current, username, password)
                if kanidm_next:
                    url = kanidm_next
                    last_detail = f"kanidm auth -> {kanidm_next}"
                    continue
            parsed_form = parse_login_form(html, current)
            if parsed_form is not None:
                action, fields = parsed_form
                payload = _fill_credentials(fields, username, password)
                result = client.post(action, data=payload)
                last_detail = f"POST {action} status={result.status_code} url={result.url}"
                if result.status_code >= 400:
                    return ProbeResult(name, False, last_detail)
                next_form = parse_login_form(result.text, str(result.url))
                if next_form is not None:
                    action, fields = next_form
                    payload = _fill_credentials(fields, username, password)
                    result = client.post(action, data=payload)
                    last_detail = f"POST {action} status={result.status_code} url={result.url}"
                    if result.status_code >= 400:
                        return ProbeResult(name, False, last_detail)
                    if parse_login_form(result.text, str(result.url)) is not None:
                        return ProbeResult(name, False, "login form still present after POST")
                url = str(result.url)
                continue
            authelia_next = authelia_first_factor(client, current, username, password)
            if authelia_next:
                url = authelia_next
                last_detail = f"authelia firstfactor -> {authelia_next}"
                continue
            sso = _sso_href(html, current)
            if sso:
                url = sso
                last_detail = f"sso href {sso}"
                continue
            body = html.lower()
            if _looks_like_login_page(html, current):
                return ProbeResult(name, False, f"login page without usable form at {current}")
            if success_host and success_host not in current:
                return ProbeResult(name, False, f"expected host {success_host} at {current}")
            if "access_token=" in current:
                return ProbeResult(name, True, last_detail)
            if success_needles and not any(needle in body for needle in success_needles):
                return ProbeResult(name, False, f"missing markers {success_needles} at {current}")
            return ProbeResult(name, True, last_detail)
        return ProbeResult(name, False, f"too many hops; {last_detail}")
    except httpx.HTTPError as exc:
        return ProbeResult(name, False, f"{type(exc).__name__}: {exc}")


def probe_forward_auth(
    client: httpx.Client,
    url: str,
    *,
    name: str,
) -> ProbeResult:
    """Anonymous GET must not be 200; a session GET after login should be 200."""
    try:
        anonymous = client.build_request("GET", url)
        # Use a client without cookies: send an isolated request.
        isolated = httpx.Client(
            timeout=client.timeout,
            verify=client._transport._pool._ssl_context is not None,
            follow_redirects=True,
        )
        try:
            isolated._transport = client._transport
            denied = isolated.send(anonymous)
        except Exception:
            denied = isolated.get(url)
        finally:
            isolated.close()
        if (
            denied.status_code == 200
            and "remote-user" not in {key.lower() for key in denied.headers}
            and "unauthorized" not in denied.text.lower()
        ):
            return ProbeResult(name, False, "anonymous GET returned 200")
        authed = client.get(url)
        if authed.status_code >= 400:
            return ProbeResult(name, False, f"authenticated GET {authed.status_code}")
        return ProbeResult(name, True, f"anon={denied.status_code} auth={authed.status_code}")
    except httpx.HTTPError as exc:
        return ProbeResult(name, False, f"{type(exc).__name__}: {exc}")


def probe_anonymous_denied(client: httpx.Client, url: str, *, name: str) -> ProbeResult:
    """GET without cookies must not serve the protected body."""
    try:
        response = httpx.get(
            url,
            follow_redirects=False,
            timeout=client.timeout,
            verify=False,  # eval uses Caddy internal TLS
        )
        if response.status_code in {401, 403, 302, 303, 307, 308}:
            return ProbeResult(name, True, f"status={response.status_code}")
        if response.status_code == 200 and "unauthorized" in response.text.lower():
            return ProbeResult(name, True, "200 with unauthorized body")
        return ProbeResult(name, False, f"status={response.status_code}")
    except httpx.HTTPError as exc:
        return ProbeResult(name, False, f"{type(exc).__name__}: {exc}")


def probe_authed_ok(
    client: httpx.Client,
    url: str,
    *,
    name: str,
    needles: tuple[str, ...] = (),
) -> ProbeResult:
    """GET with the session client must be 200."""
    try:
        response = client.get(url)
        if response.status_code >= 400:
            return ProbeResult(name, False, f"status={response.status_code}")
        body = response.text.lower()
        if needles and not any(needle in body for needle in needles):
            return ProbeResult(name, False, f"missing markers {needles} at {response.url}")
        return ProbeResult(name, True, f"status={response.status_code} url={response.url}")
    except httpx.HTTPError as exc:
        return ProbeResult(name, False, f"{type(exc).__name__}: {exc}")


def audit_from_logs(logs: Mapping[str, str], needles: tuple[str, ...]) -> ProbeResult:
    """Pass when any service log contains an audit needle."""
    blob = "\n".join(logs.values()).lower()
    hit = next((needle for needle in needles if needle.lower() in blob), None)
    if hit:
        return ProbeResult("audit_log", True, f"matched {hit!r}")
    return ProbeResult("audit_log", False, "no audit needle in docker logs")
