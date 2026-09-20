"""Choose proxy, IdP, CA, and OpenRemote from measured results."""

import json
from pathlib import Path
from typing import Any

from ss_control.eval.models import CandidateResult

REQUIRED_PROBES = (
    "oidc_grafana",
    "oidc_chirpstack",
    "oidc_nodered",
    "forward_auth_streamlit",
    "forward_auth_frigate",
    "jwt_ss_kit_web",
    "mtls_accept",
    "mtls_reject",
    "audit_log",
)

COMPOSITION_NEEDS = (
    "registry_api",
    "fusion_incidents",
    "oidc_grafana",
    "oidc_chirpstack",
    "oidc_nodered",
)


def _passed(result: CandidateResult, name: str) -> bool:
    item = result.probe_map().get(name)
    return bool(item and item.passed)


def _all_passed(result: CandidateResult, names: tuple[str, ...]) -> bool:
    return all(_passed(result, name) for name in names)


def select_stack(results: list[CandidateResult]) -> dict[str, Any]:
    """Deterministic selection. Keycloak is the valid negative fallback."""
    by_id = {item.candidate_id: item for item in results}
    composition = [
        item for item in results if item.candidate_id.endswith("-composition") and not item.error
    ]
    viable = [item for item in composition if _all_passed(item, REQUIRED_PROBES)]
    if viable:
        chosen = min(
            viable, key=lambda item: (item.peak.rss_mib if item.peak else 1e12, item.candidate_id)
        )
        idp = chosen.candidate_id.split("-", 1)[0]
        reason = "lightest composition candidate that passed every requirement"
    elif composition:
        ranked = sorted(
            composition,
            key=lambda item: (
                -sum(1 for probe in item.probes if probe.passed),
                item.peak.rss_mib if item.peak else 1e12,
            ),
        )
        chosen = ranked[0]
        idp = "keycloak"
        reason = (
            "no composition candidate passed every requirement; "
            "valid negative is Keycloak on the nettop"
        )
        if "keycloak-composition" in by_id and not by_id["keycloak-composition"].error:
            chosen = by_id["keycloak-composition"]
    else:
        chosen = None
        idp = "keycloak"
        reason = "no composition candidate produced measurements; valid negative is Keycloak"

    openremote = by_id.get("openremote-keycloak")
    composition_ok = any(_all_passed(item, COMPOSITION_NEEDS) for item in composition)
    openremote_ok = bool(
        openremote
        and not openremote.error
        and (_passed(openremote, "oidc_grafana") or _passed(openremote, "openremote_ui"))
    )
    replace_openremote = composition_ok
    if not composition_ok and openremote_ok:
        replace_openremote = False
        reason = f"{reason}; OpenRemote kept as an optional profile because composition missed operator needs"

    decision = {
        "proxy": "caddy",
        "identity_provider": idp,
        "ca": "step-ca",
        "openremote": "replaced" if replace_openremote else "optional-profile",
        "reason": reason,
        "selected_candidate": None if chosen is None else chosen.candidate_id,
        "composition_operator_needs": composition_ok,
        "required_probes": list(REQUIRED_PROBES),
    }
    return decision


def write_report(
    dest: Path,
    *,
    results: list[CandidateResult],
    cadence: dict[str, Any],
    decision: dict[str, Any],
    host: dict[str, Any],
) -> None:
    """Write comparison.json for the specification table."""
    payload = {
        "host": host,
        "decision": decision,
        "cadence": cadence,
        "candidates": [item.as_dict() for item in results],
    }
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
