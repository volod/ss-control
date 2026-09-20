"""Docker Compose helpers for the evaluation."""

import json
import logging
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path

import httpx

from ss_control.eval.models import COMPOSE_WAIT_SEC
from ss_control.eval.stats import ResourceSample, summarize_stats

_LOG = logging.getLogger(__name__)


class ComposeError(RuntimeError):
    """A docker compose command failed."""


def compose_argv(
    files: Sequence[Path],
    *,
    project: str,
    env_file: Path,
) -> list[str]:
    """Return the base `docker compose` argv for a candidate."""
    argv = ["docker", "compose", "-p", project, "--env-file", str(env_file)]
    for file in files:
        argv.extend(["-f", str(file)])
    return argv


def run_compose(
    files: Sequence[Path],
    args: Sequence[str],
    *,
    project: str,
    env_file: Path,
    timeout_sec: int = 600,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run `docker compose ...` and return the completed process."""
    argv = [*compose_argv(files, project=project, env_file=env_file), *args]
    _LOG.info("compose %s", " ".join(args))
    result = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    if check and result.returncode != 0:
        raise ComposeError(
            f"compose {' '.join(args)} failed ({result.returncode}): {result.stderr[-2000:]}"
        )
    return result


def wait_http(
    url: str,
    *,
    timeout_sec: float = COMPOSE_WAIT_SEC,
    verify: bool = False,
    ok_codes: tuple[int, ...] = (200, 302, 303, 307, 308, 401, 403),
) -> None:
    """Poll URL until it responds with an acceptable status or raise."""
    deadline = time.monotonic() + timeout_sec
    last = "not attempted"
    with httpx.Client(verify=verify, follow_redirects=False, timeout=5.0) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(url)
                if response.status_code in ok_codes:
                    return
                last = f"status {response.status_code}"
            except httpx.HTTPError as exc:
                last = str(exc)
            time.sleep(2)
    raise ComposeError(f"timeout waiting for {url}: {last}")


def sample_stats(project: str) -> ResourceSample:
    """One `docker stats --no-stream` snapshot for a compose project."""
    listing = subprocess.run(
        [
            "docker",
            "ps",
            "-q",
            "--filter",
            f"label=com.docker.compose.project={project}",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    ids = [line.strip() for line in listing.stdout.splitlines() if line.strip()]
    if not ids:
        return ResourceSample(cpu_pct=0.0, rss_mib=0.0)
    result = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", *ids],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    rows = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return summarize_stats(rows, project=project)


def collect_logs(project: str, dest: Path, tail: int = 200) -> dict[str, str]:
    """Write compose logs to dest and return per-service excerpts."""
    dest.mkdir(parents=True, exist_ok=True)
    listing = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--format",
            "{{.Names}}",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    excerpts: dict[str, str] = {}
    for name in listing.stdout.splitlines():
        name = name.strip()
        if not name:
            continue
        log = subprocess.run(
            ["docker", "logs", "--tail", str(tail), name],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        text = (log.stdout or "") + (log.stderr or "")
        (dest / f"{name}.log").write_text(text, encoding="utf-8")
        excerpts[name] = text[-4000:]
    return excerpts
