# ss-control

Site control plane: the only human ingress, single sign-on, and the site CA.

This directory is staged in the selfsuvis repository until it is exported. It is compose, config,
and scripts. Evaluation selected Caddy, Authelia, and step-ca, and replaced OpenRemote with
composition. Production compose is `docker-compose.yml`; the measurement harness lives under
`eval/`.

## Commands

| Command | Does |
| --- | --- |
| `make ci` | Locked install, lint, unit tests, documentation checks |
| `make credentials` | Generate `.env.secrets` if missing and print the summary |
| `make up` | Start Caddy (80/443), Authelia, step-ca, Grafana, Node-RED, Prometheus, cAdvisor |
| `make probe` | OIDC login to Grafana, MQTT mTLS accept/reject, published-port check |
| `make enrol KIND=client NAME=mqtt-1` | Issue a site-CA certificate |
| `make down` | Stop the compose project (keeps certs and secrets) |
| `make eval` | Start each candidate stack, probe SSO/mTLS, sample `docker stats` |
| `make eval-down` | Stop leftover evaluation compose projects |

Runtime data is written to `$DATA_DIR/ss-control/`. Secrets are gitignored `.env.secrets`.
