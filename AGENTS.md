# AGENTS.md project rules

This file is the canonical instruction source for every coding agent in this repository.

## Development guardrails

- **Git:** Do not commit, push, rewrite history, or revert user changes unless explicitly asked.
- **Python:** Support Python 3.11 or newer. Use `uv`, `uv.lock`, and `pyproject.toml`. Before a
  direct `uv` command, source `scripts/shared/common.sh` and run `ssc_load_env`.
- **Typing:** Keep production code typed. Do not add `from __future__ import annotations`.
- **Paths:** Never hardcode machine-specific absolute paths. Resolve from the project root and
  honor `.env` and `DATA_DIR`. Runtime output belongs under `$DATA_DIR/ss-control/`.
- **Secrets:** Never commit credentials. Evaluation secrets are generated into `$DATA_DIR`.
- **ASCII:** Use ASCII in logs, docs, comments, and generated shell output.

## Package rules

ss-control is compose, config, and scripts: a reverse proxy, an identity provider, a site CA,
observability, and Node-RED. It contains no application logic, media parsing, or radio decoding.
The Python package `ss_control` is the evaluation harness and later operator helpers.

Import only this package and ss-common (`volod/ss-common` tag `v0.1.0`). `[tool.ss-split]
siblings = []`.

## Tests and quality

`make ci` is the required gate: locked install, format, lint, unit tests, documentation links,
and spec-plan integrity. `make eval` is the measured identity-provider run and needs Docker; it
is not part of `make ci`.

## Documentation lifecycle

| Question | Source of truth |
| --- | --- |
| What should the product do? | `docs/design/spec.md` |
| What work remains? | `docs/impl/plan.md` |
| What exists and where? | `docs/impl/current.md` |
| How is work performed? | `docs/guide/` and this file |

The parent repository still owns `stage-ss-control` until this project is published.
