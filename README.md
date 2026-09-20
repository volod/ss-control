# ss-control

Site control plane: the only human ingress, single sign-on, and the site CA.

This directory is staged in the selfsuvis repository until it is exported. It is compose, config,
and scripts. Evaluation selected Caddy, Authelia, and step-ca, and replaced OpenRemote with
composition. The measurement harness lives under `eval/`; production compose is
`stage-ss-control`.

## Commands

| Command | Does |
| --- | --- |
| `make ci` | Locked install, lint, unit tests, documentation checks |
| `make eval` | Start each candidate stack, probe SSO/mTLS, sample `docker stats` |
| `make eval-down` | Stop leftover evaluation compose projects |

Measurements are written to `$DATA_DIR/ss-control/eval/<run-id>/`.
