"""Release-cadence numbers from GitHub release pages."""

import json
import logging
import statistics
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ss_control.eval.models import CADENCE_REPOS

_LOG = logging.getLogger(__name__)
_API = "https://api.github.com/repos/{owner}/{repo}/releases?{query}"
_USER_AGENT = "ss-control-eval/0.1"


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def cadence_days(published: list[str]) -> dict[str, Any]:
    """Median and mean days between consecutive release timestamps (newest first)."""
    times = sorted((_parse_time(item) for item in published if item), reverse=True)
    if len(times) < 2:
        return {"releases": len(times), "median_days": None, "mean_days": None}
    gaps = [
        (times[index] - times[index + 1]).total_seconds() / 86400.0
        for index in range(len(times) - 1)
    ]
    return {
        "releases": len(times),
        "median_days": round(statistics.median(gaps), 1),
        "mean_days": round(statistics.mean(gaps), 1),
        "newest": times[0].date().isoformat(),
        "oldest_in_window": times[-1].date().isoformat(),
    }


def fetch_release_dates(
    owner: str, repo: str, *, limit: int = 15, timeout_sec: float = 20.0
) -> list[str]:
    """Return `published_at` values from the GitHub releases API."""
    url = _API.format(owner=owner, repo=repo, query=urlencode({"per_page": str(limit)}))
    request = Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"}
    )
    with urlopen(request, timeout=timeout_sec) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"unexpected GitHub payload for {owner}/{repo}")
    dates = [str(item.get("published_at") or "") for item in payload if not item.get("draft")]
    return [item for item in dates if item]


def collect_cadence() -> dict[str, Any]:
    """Fetch cadence for every tracked upstream. Failures are recorded, not raised."""
    out: dict[str, Any] = {}
    for name, owner, repo in CADENCE_REPOS:
        try:
            dates = fetch_release_dates(owner, repo)
            row = cadence_days(dates)
            row["repo"] = f"{owner}/{repo}"
            out[name] = row
        except Exception as exc:
            _LOG.warning("cadence fetch failed for %s/%s: %s", owner, repo, exc)
            out[name] = {"repo": f"{owner}/{repo}", "error": str(exc)}
    return out
