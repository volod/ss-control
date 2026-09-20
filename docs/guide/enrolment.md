# Enrolment

step-ca is the site CA. `make up` issues the Caddy server certificate, the Mosquitto server
certificate, and an MQTT probe client. Additional leaves:

```bash
make enrol KIND=client NAME=ss-sens
make enrol KIND=service NAME=fusion-rt
./scripts/ss-control/ss-control-enrol.sh client mqtt-sensor-01
./scripts/ss-control/ss-control-enrol.sh service fusion-rt --san fusion-rt --san localhost
```

Certificates land under `$DATA_DIR/ss-control/certs/`:

| Path | Use |
| --- | --- |
| `root_ca.crt` | Trust store for every client |
| `server.crt` / `server.key` | Mosquitto TLS listener |
| `caddy.crt` / `caddy.key` | Human ingress |
| `client.crt` / `client.key` | MQTT probe client (`MQTT_CLIENT_NAME`) |
| `clients/<name>/` | Extra Mosquitto clients |
| `services/<name>/` | Service-to-service leaves |

Mosquitto (`use_identity_as_username true`) treats the certificate CN as the username.
A client without a site-CA certificate is dropped at TLS; a valid leaf receives CONNACK 0.

The published [ss-sens](https://github.com/volod/ss-sens) tag `v0.1.0` still runs its own
Mosquitto with password users. To consume this site CA, copy `root_ca.crt` plus a client pair
into the ss-sens certs dir, set `require_certificate true`, and keep the ss-sens broker off
the host network if ss-control already publishes 80/443 as the only human ingress.

Leaf duration is 2160h (90 days). `make up` raises the step-ca provisioner
`maxTLSCertDuration` from the image default of 24h.
