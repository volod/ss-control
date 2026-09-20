"""Orchestrate candidate compose stacks and write the evaluation report."""

import contextlib
import logging
import os
import platform
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from ss_control.eval import cadence as cadence_mod
from ss_control.eval.ca import issue_certs
from ss_control.eval.caddyfile import render_caddyfile
from ss_control.eval.compose import collect_logs, run_compose, sample_stats, wait_http
from ss_control.eval.envfile import compose_env, oidc_urls, write_env_file
from ss_control.eval.hosts import install_eval_dns
from ss_control.eval.http_probe import audit_from_logs
from ss_control.eval.idp_files import render_candidate_configs
from ss_control.eval.kanidm_setup import bootstrap_kanidm
from ss_control.eval.models import (
    CANDIDATES,
    COMPOSE_WAIT_SEC,
    IDLE_SAMPLE_SEC,
    IMAGES,
    OPENREMOTE_HTTPS_PORT,
    PEAK_SAMPLE_SEC,
    PROXY_HTTPS_PORT,
    STATS_INTERVAL_SEC,
    Candidate,
    CandidateResult,
    public_url,
)
from ss_control.eval.probes_run import run_probes
from ss_control.eval.report import select_stack, write_report
from ss_control.eval.secrets import generate_secrets, write_secrets
from ss_control.eval.stats import mean_sample, peak_sample

_LOG = logging.getLogger(__name__)


def project_root() -> Path:
    """ss-control repository root (contains eval/ and pyproject.toml)."""
    return Path(__file__).resolve().parents[3]


def data_root() -> Path:
    """`$DATA_DIR/ss-control` resolved against the project root when relative."""
    raw = os.environ.get("DATA_DIR", str(project_root() / ".data"))
    path = Path(raw)
    if not path.is_absolute():
        path = project_root() / path
    return path / "ss-control"


def compose_files(candidate: Candidate, root: Path) -> list[Path]:
    compose = root / "eval" / "compose"
    if candidate.baseline == "openremote":
        return [compose / "openremote.yml"]
    files = [compose / "base.yml"]
    if candidate.idp == "keycloak":
        files.append(compose / "idp-keycloak.yml")
    elif candidate.idp == "authelia":
        files.append(compose / "idp-authelia.yml")
    else:
        files.append(compose / "idp-kanidm.yml")
    return files


def _hash_authelia_password(password: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            IMAGES["authelia"],
            "authelia",
            "crypto",
            "hash",
            "generate",
            "pbkdf2",
            "--variant",
            "sha512",
            "--password",
            password,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("$"):
            return line
        if "Digest:" in line:
            return line.split("Digest:", 1)[1].strip()
    raise RuntimeError("authelia hash output had no digest")


def _sample_period(project: str, seconds: int) -> list:
    samples = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        samples.append(sample_stats(project))
        time.sleep(STATS_INTERVAL_SEC)
    return samples


def _down(files: list[Path], project: str, env_file: Path) -> None:
    run_compose(
        files, ["down", "-v", "--remove-orphans"], project=project, env_file=env_file, check=False
    )


def run_candidate(
    candidate: Candidate,
    *,
    run_dir: Path,
    secrets: dict[str, str],
    root: Path,
) -> CandidateResult:
    """Bring up one candidate, measure it, probe it, and tear it down."""
    project = "ssce" + candidate.id.replace("-", "")[:20]
    work = run_dir / candidate.id
    config_dir = work / "config"
    data_dir = work / "data"
    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in ("step-ca", "certs", "kanidm", "authelia"):
        path = data_dir / name
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o777)
    urls = oidc_urls(candidate.idp)
    authelia_hash = ""
    if candidate.idp == "authelia":
        authelia_hash = _hash_authelia_password(secrets["admin_password"])
    render_candidate_configs(
        config_dir,
        candidate,
        secrets,
        issuer=urls["CHIRPSTACK_PROVIDER"],
        token_url=urls["OIDC_TOKEN_URL"],
        authelia_password_hash=authelia_hash,
    )
    (config_dir / "Caddyfile").write_text(render_caddyfile(candidate), encoding="utf-8")
    env = compose_env(
        project=project,
        config_dir=config_dir,
        data_dir=data_dir,
        eval_root=root,
        secrets=secrets,
        idp=candidate.idp if candidate.idp != "openremote" else "keycloak",
    )
    env_file = work / "compose.env"
    write_env_file(env_file, env)
    files = compose_files(candidate, root)
    result = CandidateResult(candidate_id=candidate.id)
    try:
        _down(files, project, env_file)
        early = ["step-ca"]
        if candidate.baseline == "composition":
            early.extend(["postgres", "redis"])
        run_compose(files, ["up", "-d", "--build", *early], project=project, env_file=env_file)
        network = f"{project}_eval"
        certs = issue_certs(
            certs_dir=data_dir / "certs",
            step_dir=data_dir / "step-ca",
            password=secrets["step_ca_password"],
            provisioner=secrets["step_provisioner"],
            network=network,
            client_name=secrets["mqtt_client_name"],
        )
        if candidate.idp == "kanidm":
            run_compose(files, ["up", "-d", "kanidm"], project=project, env_file=env_file)
            try:
                bootstrap_kanidm(
                    project=project, network=network, secrets=secrets, data_dir=data_dir
                )
            except Exception as exc:
                _LOG.exception("kanidm bootstrap failed")
                result.logs_excerpt = f"kanidm bootstrap: {type(exc).__name__}: {exc}"
            render_candidate_configs(
                config_dir,
                candidate,
                secrets,
                issuer=oidc_urls("kanidm")["CHIRPSTACK_PROVIDER"],
                token_url=oidc_urls("kanidm")["OIDC_TOKEN_URL"],
            )
            env.update(
                compose_env(
                    project=project,
                    config_dir=config_dir,
                    data_dir=data_dir,
                    eval_root=root,
                    secrets=secrets,
                    idp="kanidm",
                )
            )
            write_env_file(env_file, env)
        run_compose(files, ["up", "-d", "--build"], project=project, env_file=env_file)
        if candidate.baseline == "composition":
            wait_http(f"{public_url('grafana')}/login", timeout_sec=COMPOSE_WAIT_SEC)
            if candidate.idp == "keycloak":
                wait_http(
                    f"{public_url('auth')}/realms/ss/.well-known/openid-configuration",
                    timeout_sec=COMPOSE_WAIT_SEC,
                )
            else:
                wait_http(public_url("auth"), timeout_sec=COMPOSE_WAIT_SEC)
            wait_http(public_url("chirpstack"), timeout_sec=COMPOSE_WAIT_SEC)
            if candidate.uses_oauth2_proxy:
                try:
                    wait_http(
                        f"{public_url('streamlit')}/oauth2/start",
                        timeout_sec=45,
                    )
                except Exception as exc:
                    _LOG.warning("oauth2-proxy not ready: %s", exc)
        else:
            wait_http(
                f"https://127.0.0.1:{OPENREMOTE_HTTPS_PORT}/",
                timeout_sec=max(COMPOSE_WAIT_SEC, 420),
            )
        _ = PROXY_HTTPS_PORT
        time.sleep(8)
        idle_samples = _sample_period(project, IDLE_SAMPLE_SEC)
        result.idle = mean_sample(idle_samples)
        with httpx.Client(verify=False, follow_redirects=True, timeout=40.0) as client:
            result.probes = run_probes(
                candidate, client=client, secrets=secrets, certs=certs, logs={}
            )
            logs = collect_logs(project, work / "logs")
            result.probes = [item for item in result.probes if item.name != "audit_log"]
            result.probes.append(
                audit_from_logs(
                    logs,
                    (
                        "login",
                        "authentication",
                        "successful authentication",
                        "AUTHENTICATE",
                        "type=LOGIN",
                        "oauth2",
                    ),
                )
            )
            peak_samples = _sample_period(project, PEAK_SAMPLE_SEC)
            # Drive a little more load during peak sampling.
            for _ in range(3):
                with contextlib.suppress(httpx.HTTPError):
                    client.get(f"{public_url('grafana')}/login")
            peak_samples.extend(_sample_period(project, 6))
            result.peak = peak_sample(peak_samples)
            result.logs_excerpt = "\n".join(list(logs.values())[:2])[:1500]
    except Exception as exc:
        _LOG.exception("candidate %s failed", candidate.id)
        result.error = f"{type(exc).__name__}: {exc}"
        with contextlib.suppress(Exception):
            result.logs_excerpt = "\n".join(collect_logs(project, work / "logs").values())[:1500]
    finally:
        _down(files, project, env_file)
    (work / "result.json").write_text(
        __import__("json").dumps(result.as_dict(), indent=2) + "\n", encoding="utf-8"
    )
    return result


def run_eval(
    *, candidates: tuple[Candidate, ...] | None = None, skip_cadence: bool = False
) -> Path:
    """Run every candidate and write `$DATA_DIR/ss-control/eval/<run-id>/`."""
    install_eval_dns()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = data_root() / "eval" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    secrets = generate_secrets()
    write_secrets(run_dir / "secrets.json", secrets)
    host = {
        "arch": platform.machine(),
        "system": platform.system(),
        "cpu": platform.processor() or platform.machine(),
        "cuda_host": True,
    }
    cadence = {} if skip_cadence else cadence_mod.collect_cadence()
    results = []
    for candidate in candidates or CANDIDATES:
        _LOG.info("starting candidate %s", candidate.id)
        results.append(
            run_candidate(candidate, run_dir=run_dir, secrets=secrets, root=project_root())
        )
    decision = select_stack(results)
    write_report(
        run_dir / "comparison.json",
        results=results,
        cadence=cadence,
        decision=decision,
        host=host,
    )
    (run_dir / "decision.json").write_text(
        __import__("json").dumps(decision, indent=2) + "\n", encoding="utf-8"
    )
    _LOG.info("evaluation written to %s", run_dir)
    return run_dir


def down_all() -> None:
    """Best-effort teardown of leftover ssce* compose projects."""
    listing = subprocess.run(
        ["docker", "compose", "ls", "-a", "--format", "json"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if listing.returncode != 0 or not listing.stdout.strip():
        return
    import json

    try:
        rows = json.loads(listing.stdout)
    except json.JSONDecodeError:
        return
    for row in rows:
        name = str(row.get("Name") or "")
        if name.startswith("ssce"):
            subprocess.run(
                ["docker", "compose", "-p", name, "down", "-v"], check=False, timeout=180
            )
