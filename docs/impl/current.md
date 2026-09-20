# Current Implementation

ss-control deploys as its own compose project: Caddy is the only human ingress (host ports 80
and 443), Authelia provides OIDC SSO and forward-auth, and step-ca issues site-CA certificates
for MQTT and service-to-service traffic.

| Need | Read |
| --- | --- |
| Production compose, commands, probes | [stack.md](current/stack.md) |
| MQTT and service enrolment | [enrolment.md](../guide/enrolment.md) |
| Secrets file and rotation | [secrets-management.md](../reference/secrets-management.md) |
| Identity provider, proxy, CA, and OpenRemote measurements | [evaluation.md](current/evaluation.md) |

## Production stack

Command: `make up` (`python -m ss_control.stack up`). Compose file: `docker-compose.yml`.
Runtime data: `$DATA_DIR/ss-control/` (`DATA_DIR=.data` in this staged tree). Secrets:
gitignored `.env.secrets` (`make credentials`).

Selected stack from the evaluation: Caddy 2.9.1, Authelia 4.39.4, step-ca 0.28.4. OpenRemote
is not a profile. Prometheus, Grafana, and cAdvisor run here (moved from the ss-sens `metrics`
profile). Node-RED is admin-only behind Authelia. Grafana, ChirpStack, and Node-RED have OIDC
clients. The ss-video UI and Frigate sit behind Caddy forward-auth; local bring-up uses
`upstream-stub` until those services are on the network.

Acceptance on this amd64 CUDA host (`$DATA_DIR/ss-control/probe/result.json`): OIDC login
reached Grafana; MQTT accepted a site-CA client certificate and rejected a connect without
one; this compose project published only 80 and 443.

## Evaluation harness

`make eval` remains the candidate measurement run. Details: [evaluation.md](current/evaluation.md).
