# Secrets management

ss-control keeps secrets out of git. Non-secret defaults live in `.env.example`. Generated
secrets live in `.env.secrets` (mode 0600) at the project root.

## Files

| Path | Git | Holds |
| --- | --- | --- |
| `.env.example` | yes | Domain, bind, upstreams, `DATA_DIR` |
| `.env` | no | Optional local overrides |
| `.env.secrets` | no | Passwords, OIDC client secrets, Authelia keys, step-ca password |
| `$DATA_DIR/ss-control/authelia/` | no | Rendered Authelia config, OIDC JWK, sqlite |
| `$DATA_DIR/ss-control/certs/` | no | Site CA leaves and `provisioner.pass` |
| `$DATA_DIR/ss-control/compose.env` | no | Compose interpolation including secrets |

`make credentials` / `python -m ss_control.stack credentials` creates `.env.secrets` when
missing (`--force` overwrites). `make up` loads it, hashes the Authelia password, and writes
runtime files under `$DATA_DIR/ss-control/`.

## Variables in `.env.secrets`

| Variable | If leaked |
| --- | --- |
| `ADMIN_PASSWORD` | Authelia and Grafana operator login |
| `GRAFANA_CLIENT_SECRET` | Grafana OIDC client |
| `CHIRPSTACK_CLIENT_SECRET` | ChirpStack OIDC client |
| `NODERED_CLIENT_SECRET` | Node-RED OIDC client |
| `AUTHELIA_JWT_SECRET` / `AUTHELIA_SESSION_SECRET` / `AUTHELIA_STORAGE_KEY` / `AUTHELIA_HMAC_SECRET` | Authelia session and OIDC signing |
| `STEP_CA_PASSWORD` | Ability to issue site-CA certificates |
| `NODERED_CREDENTIAL_SECRET` | Node-RED credential encryption |

Video, fusion, and API secrets stay in the parent selfsuvis repository until that tree
flattens to ss-video. ss-sens secrets stay in the published ss-sens repository.

## Rotation

1. `python -m ss_control.stack credentials --force` (or edit `.env.secrets`).
2. `make down && make up` so Authelia and Grafana reload.
3. Re-enrol MQTT clients if the CA provisioner password changed (`make up` keeps the same
   step-ca volume unless you pass `--volumes` to `make down`).

There is no in-process hot reload.
