# Site control evaluation

The evaluation harness compared Keycloak, Kanidm, and Authelia behind Caddy, with step-ca as the
site CA, against a composition baseline (Grafana, ChirpStack UI, Node-RED, registry and fusion-rt
stubs) and an OpenRemote plus Keycloak baseline.

Command: `make eval` (`python -m ss_control.eval run`). Candidate compose files live under
`eval/`. Measurements are written to `$DATA_DIR/ss-control/eval/<run-id>/` (`DATA_DIR=.data` in
this staged tree). Unit tests cover stats parsing, JWT validation through `ss_kit.web.jwt`, MQTT
CONNECT encoding, cadence math, report selection, Authelia client auth, and Kanidm secret/consent
parsing; they do not start Docker.

Host: amd64 CUDA Linux. Arm64 numbers come from the ss-sens Pi edge soak when that soak exists;
they are not required to close this evaluation.

## Decision

| Field | Value |
| --- | --- |
| Proxy | Caddy 2.9.1 |
| Identity provider | Authelia 4.39.4 |
| Site CA | step-ca 0.28.4 |
| OpenRemote | replaced by composition |
| Selected candidate | `authelia-composition` |
| Reason | lightest composition candidate that passed every requirement |

Combined decision JSON:
`$DATA_DIR/ss-control/eval/20260920T073500Z/comparison.json`.

Keycloak 26.3.3 passed every required probe at about 1.1 GiB RSS and is the valid-negative
fallback. Kanidm 1.6.4 passed Grafana, ChirpStack, mTLS, and audit; it failed Node-RED userinfo,
oauth2-proxy forward-auth, JWT client_credentials, and therefore the composition registry/fusion
checks that sit behind forward-auth. The OpenRemote plus Keycloak candidate timed out on
`https://127.0.0.1:19443/` with HTTP 503 for 420 s (Keycloak `LOGIN_ERROR
invalid_user_credentials` for the admin user; manager started late then stopped). Composition
already covers operator needs, so OpenRemote is not kept as an optional profile.

## Resource table

| Candidate | Run | Idle CPU % | Idle RSS MiB | Peak CPU % | Peak RSS MiB | IdP idle RSS MiB |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| keycloak-composition | `20260919T210546Z` | 8.91 | 1091.8 | 17.17 | 1082.0 | 839.4 |
| authelia-composition | `20260920T045017Z` | 11.53 | 260.7 | 5.47 | 268.7 | 32.6 |
| kanidm-composition | `20260920T051600Z` | 10.12 | 289.8 | 7.39 | 297.6 | 51.4 |
| openremote-keycloak | `20260920T051811Z` | -- | -- | -- | -- | -- |

Peak RSS can sit slightly below idle RSS; both values are `docker stats` samples, not a
guarantee that peak is a maximum.

## Probe table

Required probes: Grafana OIDC, ChirpStack OIDC, Node-RED OIDC, Streamlit forward-auth, Frigate
forward-auth, JWT through `ss_kit.web`, MQTT mTLS accept, MQTT mTLS reject, audit log.
Composition operator needs also require registry API and fusion-rt incidents.

| Candidate | Grafana | ChirpStack | Node-RED | Streamlit FA | Frigate FA | JWT | mTLS accept | mTLS reject | Audit | Registry | Fusion |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| keycloak-composition | pass | pass | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| authelia-composition | pass | pass | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| kanidm-composition | pass | pass | fail | fail | fail | fail | pass | pass | pass | fail | fail |
| openremote-keycloak | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |

Honest notes (not failures on the selected stack):

- Authelia JWT access tokens validated as RS256 JWTs; the `sub` claim was empty on the
  client_credentials token used by the eval-cli client (`jwt_ss_kit_web` still passed).
- Authelia uses native forward-auth (no oauth2-proxy). Keycloak and Kanidm use oauth2-proxy.
- Streamlit, Frigate, registry, and fusion-rt were HTTP stubs, not the production UIs.
- ChirpStack 4.12 OIDC uses `user_authentication.enabled="openid_connect"` and finishes the SPA
  callback through gRPC-web `InternalService.OpenIdConnectLogin`.
- Kanidm Node-RED failed with userinfo `invalid_request` (HTTP 400). Kanidm forward-auth stayed
  at HTTP 401. Kanidm token endpoint rejected client_credentials / password grant (HTTP 422).
- OpenRemote official service names (`postgresql`, `keycloak`, `manager`, `proxy`) were used;
  the stack still did not become ready in 420 s.

## Upstream release cadence

Last 15 GitHub releases, collected 2026-09-20:

| Component | Repository | Releases | Median days | Mean days | Newest |
| --- | --- | ---: | ---: | ---: | --- |
| Caddy | caddyserver/caddy | 15 | 23.2 | 37.0 | 2026-06-03 |
| Keycloak | keycloak/keycloak | 15 | 14.0 | 103.6 | 2026-09-16 |
| Kanidm | kanidm/kanidm | 15 | 7.5 | 15.2 | 2026-09-11 |
| Authelia | authelia/authelia | 15 | 2.5 | 22.3 | 2026-09-17 |
| step-ca | smallstep/certificates | 15 | 3.1 | 26.4 | 2026-03-23 |
| OpenRemote | openremote/openremote | 15 | 8.5 | 8.9 | 2026-09-02 |

## Pinned eval images

See `IMAGES` in `src/ss_control/eval/models.py`. Notable pins: `caddy:2.9.1-alpine`,
`authelia/authelia:4.39.4`, `quay.io/keycloak/keycloak:26.3.3`, `kanidm/server:1.6.4`,
`smallstep/step-ca:0.28.4`, `smallstep/step-cli:0.28.3`, `grafana/grafana:11.6.3`,
`nodered/node-red:4.0.9`, `chirpstack/chirpstack:4.12.1`, `eclipse-mosquitto:2.0.21`,
`quay.io/oauth2-proxy/oauth2-proxy:v7.8.2`. OpenRemote images were `openremote/{proxy,keycloak,manager,postgresql}:latest`.

Host ports used by the harness (not production): HTTPS 18443, HTTP 18080, MQTT TLS 19883,
OpenRemote HTTPS 19443. Eval DNS is `*.ss-control.test`.

## Field-device follow-up

Published [ss-sens](https://github.com/volod/ss-sens) tag `v0.1.0` still documents OpenRemote.
That tag is not edited from this repository. When the ss-sens plan continues: drop
`openremote-asset-sync`; `operator-dashboard-acceptance` uses Grafana and Node-RED behind
ss-control SSO.

Production compose is `stage-ss-control` (not this evaluation).
