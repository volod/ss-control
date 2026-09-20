# Implementation Plan (forward work)

Forward-only: this file describes work that remains. Available behavior belongs in
[current-state documentation](current.md). Product behavior belongs in the
[specification](../design/spec.md).

## Agent Implementation Tasks

### Site control plane -- `site-control-plane`

#### stage-ss-control

Sites need one human ingress, single sign-on, and machine certificates before operator tooling is
exposed.

- Serves: `site-control-plane` -- [Site control plane](../design/spec.md#site-control-plane)
- Agent status: RUN NEEDED
- Dependencies: none.
- User-visible outcome: ss-control deploys as its own compose project that is the only human
  ingress, provides SSO for every UI and API, and issues site-CA certificates for MQTT and
  service-to-service traffic.
- Scope boundary: in scope -- production compose from the evaluation decision: Caddy, Authelia,
  and step-ca; composition operator UIs (Grafana, ChirpStack, Node-RED); no OpenRemote profile;
  enrolment scripts; Prometheus, Grafana, and cAdvisor; Node-RED, admin-only behind Authelia; CPU
  and memory reservations; secrets generated into `.env.secrets`. Out of scope -- application
  code; any exposed port other than 443 and the 80 redirect.
- Data and artifact paths: `eval/` is the measurement harness; production compose lands at the
  repository root. Runtime data under `$DATA_DIR/ss-control/`.
- Execution path: `make up`, then integration tests: OIDC login to Grafana; MQTT connect with and
  without a site-CA client certificate; a port scan of the host.
- Acceptance gates: OIDC login reaches Grafana; MQTT rejects a client without a site-CA
  certificate and accepts one with it; the port scan shows only 80 and 443 from this project.
- Documentation target: [current.md](current.md).

## Human-Assisted Tasks

No open human-lane work in this repository while it is staged. Publishing is owned by the parent
repository.
