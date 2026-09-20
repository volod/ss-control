# Production stack

ss-control is compose, config, and scripts. Application logic, media parsing, and radio
decoding stay out of this repository.

## Services

| Service | Role | Host ports |
| --- | --- | --- |
| Caddy 2.9.1 | Reverse proxy, HTTP to HTTPS redirect | 80, 443 |
| Authelia 4.39.4 | OIDC issuer and forward-auth | none |
| step-ca 0.28.4 | Site CA | none |
| Grafana 11.6.3 | Dashboards, OIDC to Authelia | none |
| Node-RED 4.0.9 | Admin automation, OIDC, Authelia `group:admins` | none |
| Prometheus v2.55.1 | Scrapes cAdvisor | none |
| cAdvisor v0.49.1 | Container metrics | none |
| Mosquitto 2.0.21 | mTLS MQTT on 8883 (compose network only) | none |
| upstream-stub | Stand-in for ss-video, Frigate, ChirpStack, fusion-rt | none |

CPU and memory reservations are `deploy.resources` on every service, overridable with
`SS_CONTROL_*_CPUS` and `SS_CONTROL_*_MEMORY`.

Caddy routes:

- `grafana.{domain}` and `chirpstack.{domain}` -- reverse proxy (native OIDC)
- `nodered.{domain}`, `video.{domain}`, `frigate.{domain}`, `fusion.{domain}`,
  `prometheus.{domain}`, `registry.{domain}` -- Authelia forward-auth then reverse proxy
- `auth.{domain}` -- Authelia
- `http://` -- permanent redirect to HTTPS

Upstream targets default to `upstream-stub:8080`. Override `SS_VIDEO_UI_UPSTREAM`,
`FRIGATE_UPSTREAM`, `CHIRPSTACK_UPSTREAM`, and `FUSION_UPSTREAM` when those compose projects
share the `ss-control` network.

## Commands

| Command | Does |
| --- | --- |
| `make credentials` | Create `.env.secrets` if missing; print URLs and the admin user |
| `make up` | Hash the Authelia password, render Authelia, start step-ca, issue certs, start the rest |
| `make probe` | Grafana OIDC, MQTT mTLS accept/reject, published-port check |
| `make enrol KIND=client NAME=<id>` | Issue a leaf certificate under `$DATA_DIR/ss-control/certs/` |
| `make down` | Stop containers; keep certs, Authelia DB, and `.env.secrets` |
| `make ci` | Lint, unit tests, documentation checks (no Docker) |

Bring-up writes `$DATA_DIR/ss-control/hosts.snippet` for `/etc/hosts`. Probes resolve
`*.ss-control.test` to loopback in-process and do not edit `/etc/hosts`.

## Modules

| Path | Role |
| --- | --- |
| `docker-compose.yml` | Production compose |
| `config/caddy/Caddyfile` | Ingress |
| `config/mosquitto/mosquitto.conf` | mTLS listener 8883 |
| `config/prometheus/prometheus.yml` | cAdvisor scrape |
| `config/grafana/provisioning/` | Prometheus datasource |
| `config/nodered/settings.js` | OIDC adminAuth |
| `src/ss_control/stack/` | Secrets, Authelia render, enrolment, probes |
| `scripts/ss-control/ss-control-credentials.sh` | Operator wrapper for `.env.secrets` |
| `scripts/ss-control/ss-control-enrol.sh` | Operator wrapper for leaf certs |

## Tests

Unit tests (`make test`, part of `make ci`) parse the compose file for published ports, check
Caddy forward-auth and Authelia OIDC clients, and check Mosquitto `require_certificate`.
They do not start Docker.

Live probes (`make probe` or `SS_CONTROL_LIVE=1 pytest tests/stack/test_live.py`) need `make up`.
Result: `$DATA_DIR/ss-control/probe/result.json`.
