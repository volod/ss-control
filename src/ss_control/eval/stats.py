"""Parse `docker stats` samples into CPU and RSS totals."""

import re
from collections.abc import Iterable

from ss_control.eval.models import ResourceSample

_MIB = 1024 * 1024
_GIB = 1024 * _MIB
_CPU = re.compile(r"([0-9.]+)\s*%")
_MEM = re.compile(r"([0-9.]+)\s*(KiB|MiB|GiB|TiB|B)", re.IGNORECASE)


def parse_cpu_pct(value: str) -> float:
    """Parse `12.34%` from docker stats."""
    match = _CPU.search(value or "")
    return float(match.group(1)) if match else 0.0


def parse_mem_bytes(value: str) -> float:
    """Parse the used side of `123.4MiB / 16GiB` into bytes."""
    used = (value or "").split("/", 1)[0].strip()
    match = _MEM.search(used)
    if match is None:
        return 0.0
    amount = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "b":
        return amount
    if unit == "kib":
        return amount * 1024
    if unit == "mib":
        return amount * _MIB
    if unit == "gib":
        return amount * _GIB
    if unit == "tib":
        return amount * _GIB * 1024
    return 0.0


def _service_name(container: str, project: str) -> str:
    prefix = f"{project}-"
    name = container[len(prefix) :] if container.startswith(prefix) else container
    if name.endswith("-1") and name.count("-") >= 1:
        name = name[: -len("-1")]
    return name


def summarize_stats(
    rows: Iterable[dict[str, str]],
    *,
    project: str,
) -> ResourceSample:
    """Sum CPU% and RSS across one `docker stats --no-stream` snapshot."""
    per_service: dict[str, dict[str, float]] = {}
    cpu_total = 0.0
    rss_total = 0.0
    for row in rows:
        name = _service_name(row.get("Name") or row.get("name") or "unknown", project)
        cpu = parse_cpu_pct(row.get("CPUPerc") or row.get("CPU %") or "0%")
        rss = parse_mem_bytes(row.get("MemUsage") or row.get("Mem Usage") or "0B")
        cpu_total += cpu
        rss_total += rss
        slot = per_service.setdefault(name, {"cpu_pct": 0.0, "rss_mib": 0.0})
        slot["cpu_pct"] = round(slot["cpu_pct"] + cpu, 2)
        slot["rss_mib"] = round(slot["rss_mib"] + rss / _MIB, 1)
    return ResourceSample(
        cpu_pct=round(cpu_total, 2),
        rss_mib=rss_total / _MIB,
        per_service=per_service,
    )


def peak_sample(samples: Iterable[ResourceSample]) -> ResourceSample:
    """Return the sample with the highest RSS, or zeros if empty."""
    chosen: ResourceSample | None = None
    for sample in samples:
        if chosen is None or sample.rss_mib > chosen.rss_mib:
            chosen = sample
    return chosen or ResourceSample(cpu_pct=0.0, rss_mib=0.0)


def mean_sample(samples: list[ResourceSample]) -> ResourceSample:
    """Mean CPU and RSS; per-service means from the last sample's keys."""
    if not samples:
        return ResourceSample(cpu_pct=0.0, rss_mib=0.0)
    cpu = sum(item.cpu_pct for item in samples) / len(samples)
    rss = sum(item.rss_mib for item in samples) / len(samples)
    services: dict[str, dict[str, float]] = {}
    names = {name for item in samples for name in item.per_service}
    for name in names:
        cpu_s = [item.per_service[name]["cpu_pct"] for item in samples if name in item.per_service]
        rss_s = [item.per_service[name]["rss_mib"] for item in samples if name in item.per_service]
        services[name] = {
            "cpu_pct": round(sum(cpu_s) / len(cpu_s), 2) if cpu_s else 0.0,
            "rss_mib": round(sum(rss_s) / len(rss_s), 1) if rss_s else 0.0,
        }
    return ResourceSample(cpu_pct=round(cpu, 2), rss_mib=rss, per_service=services)
