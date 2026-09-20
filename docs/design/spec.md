# ss-control Specification

## Purpose

ss-control is the site control plane: the only human ingress, the identity provider, the site CA,
observability, and admin automation. It is compose, config, and scripts. It contains no
application logic, media parsing, or radio decoding.

The specification is living. A need discovered during implementation expands it through
[Extending this specification](#extending-this-specification).

## Site control plane

**Problem.** Sites have no deployed identity provider and no single human ingress. Operators still
need an asset view, dashboards, alarms, and automation, and a Pi cannot host JVM services.

**Behavior.** ss-control deploys as its own compose project:

- a reverse proxy that is the only human ingress;
- an identity provider with OIDC single sign-on for every UI and API; UIs without native OIDC
  (Streamlit, Frigate) sit behind the proxy's forward-auth;
- a site CA issuing device and service certificates for MQTT and service-to-service mTLS;
- Prometheus, Grafana, and log collection;
- Node-RED, admin-only behind the identity provider because it can execute code.

It runs with reserved CPU and memory on the nettop, or on a small separate host for hardened
sites. OpenRemote is replaced by composition: the device registry API and the ChirpStack UI for
the asset view, Grafana for dashboards and alerts, Node-RED for automation, and fusion-rt
incidents for alarms.

**Decision (amd64 CUDA Linux).** Proxy Caddy 2.9.1, identity provider Authelia 4.39.4, site CA
step-ca 0.28.4. OpenRemote is replaced. Authelia was the lightest composition candidate that
passed every required probe. Keycloak passed the same probes at higher RAM (valid-negative
fallback). Kanidm did not pass every requirement. The OpenRemote plus Keycloak candidate did not
become ready. Full table: [evaluation](../impl/current/evaluation.md).

| Candidate | Idle RSS MiB | Peak RSS MiB | Required probes |
| --- | ---: | ---: | --- |
| keycloak-composition | 1091.8 | 1082.0 | all pass |
| authelia-composition (selected) | 260.7 | 268.7 | all pass |
| kanidm-composition | 289.8 | 297.6 | Node-RED, forward-auth, JWT, registry, fusion fail |
| openremote-keycloak | -- | -- | compose timeout (HTTP 503) |

**Boundary.** No application logic, no media parsing, no radio decoding. OpenRemote is not an
optional profile.

**Evaluation.** Candidate identity providers (Keycloak, Kanidm, Authelia) behind Caddy, with
step-ca as the site CA, were measured for idle and peak CPU and RAM on this amd64 host. SSO works
for Grafana, ChirpStack, and Node-RED on the selected stack. MQTT rejects clients without a
site-CA certificate. The audit log records logins. Valid negative recorded: Keycloak on the
nettop if Authelia were unavailable; OpenRemote is not kept because composition covers operator
needs.

## Capability Registry

Every capability appears here exactly once. Status is `planned` when the capability is specified
and has open plan work, or `shipped` when current-state documentation describes it.

| # | Capability | Status | How it is evaluated | Implementation |
| --- | --- | --- | --- | --- |
| 1 | `site-control-plane` | planned | Measured resource table; SSO, mTLS, and audit checks | -- |

## Extending this specification

A capability gap is a product discovery, not an automatic refusal and not permission for silent
scope growth. Use this lifecycle in order:

1. State the problem in operator or domain terms.
2. Amend the owning section of this specification, including what the capability does not do.
3. Declare the measurement, acceptance signal, and valid negative result before implementation.
4. Add a `planned` registry row with that evaluation.
5. Put tasks under the capability in the implementation line; every task declares `Serves`.
6. Build and evaluate, document available behavior under current state, remove finished plan
   scope, and change the registry row to `shipped` with its implementation link.
