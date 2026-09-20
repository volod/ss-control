# Current Implementation

ss-control is staged as compose, config, and an evaluation harness. Production ingress is not
deployed yet (`stage-ss-control`).

| Need | Read |
| --- | --- |
| Identity provider, proxy, CA, and OpenRemote measurements | [evaluation.md](current/evaluation.md) |

## Evaluation result

Measured on amd64 CUDA Linux. Selected stack: Caddy 2.9.1, Authelia 4.39.4, step-ca 0.28.4.
OpenRemote is replaced by composition (Grafana, ChirpStack UI, Node-RED, registry and fusion-rt).
Authelia was the lightest composition candidate that passed every required probe (idle 260.7 MiB
RSS, peak 268.7 MiB RSS). Keycloak passed the same probes at about 1.1 GiB RSS. Kanidm did not
pass every probe. OpenRemote plus Keycloak did not become ready.

Details, resource table, probe table, cadence, and run ids: [evaluation.md](current/evaluation.md).
Specification: [Site control plane](../design/spec.md#site-control-plane).

## Evaluation harness

`make eval` runs `python -m ss_control.eval run`. Candidate compose files live under `eval/`.
Measurements are written to `$DATA_DIR/ss-control/eval/<run-id>/`. Unit tests cover stats parsing,
JWT validation through `ss_kit.web.jwt`, MQTT CONNECT encoding, cadence math, and report
selection; they do not start Docker.
