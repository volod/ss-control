"""Live stack probes. Skipped unless SS_CONTROL_LIVE=1 after `make up`."""

import os

import pytest

from ss_control.stack.paths import secrets_path
from ss_control.stack.runner import probe
from ss_control.stack.secrets import load_secrets

pytestmark = pytest.mark.skipif(
    os.environ.get("SS_CONTROL_LIVE") != "1",
    reason="set SS_CONTROL_LIVE=1 after make up",
)


def test_live_acceptance_probes() -> None:
    secrets = load_secrets(secrets_path())
    assert secrets["ADMIN_PASSWORD"]
    report = probe()
    failed = [item.name for item in report.probes if not item.passed]
    assert report.passed(), f"failed={failed} probes={[item.as_dict() for item in report.probes]}"
