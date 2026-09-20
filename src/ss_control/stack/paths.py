"""Project and data directory helpers for the production stack."""

import os
from pathlib import Path


def project_root() -> Path:
    """ss-control repository root (contains docker-compose.yml)."""
    return Path(__file__).resolve().parents[3]


def data_root() -> Path:
    """`$DATA_DIR/ss-control` resolved against the project root when relative."""
    raw = os.environ.get("DATA_DIR", str(project_root() / ".data"))
    path = Path(raw)
    if not path.is_absolute():
        path = project_root() / path
    return path / "ss-control"


def secrets_path() -> Path:
    """Gitignored operator secrets file at the project root."""
    return project_root() / ".env.secrets"


def compose_file() -> Path:
    """Production compose file."""
    return project_root() / "docker-compose.yml"
