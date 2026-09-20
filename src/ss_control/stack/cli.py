"""Command line for the production site-control stack."""

import argparse
import logging
import sys

from ss_control.stack.ca import enrol_named
from ss_control.stack.paths import data_root, secrets_path
from ss_control.stack.runner import down, probe, up
from ss_control.stack.secrets import credentials_summary, load_or_create_secrets, load_secrets


def main(argv: list[str] | None = None) -> int:
    """Credentials, up, down, enrol, and acceptance probes."""
    parser = argparse.ArgumentParser(prog="ss-control")
    sub = parser.add_subparsers(dest="command", required=True)
    cred = sub.add_parser("credentials", help="create or print .env.secrets")
    cred.add_argument("--force", action="store_true", help="overwrite .env.secrets")
    cred.add_argument("--list", action="store_true", help="print the credentials summary")
    sub.add_parser("up", help="render config, start the compose project, issue certs")
    down_p = sub.add_parser("down", help="stop the compose project")
    down_p.add_argument("--volumes", action="store_true", help="also remove named volumes")
    enrol = sub.add_parser("enrol", help="issue a Mosquitto client or service certificate")
    enrol.add_argument("kind", choices=("client", "service"))
    enrol.add_argument("name")
    enrol.add_argument("--san", action="append", default=[], dest="sans")
    enrol.add_argument("--force", action="store_true")
    sub.add_parser("probe", help="OIDC Grafana, MQTT mTLS, published ports")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "credentials":
        values = load_or_create_secrets(secrets_path(), force=args.force)
        if args.list or not args.force:
            sys.stdout.write(credentials_summary(values))
        return 0
    if args.command == "up":
        up()
        secrets = load_secrets(secrets_path())
        sys.stdout.write(credentials_summary(secrets))
        return 0
    if args.command == "down":
        down(volumes=args.volumes)
        return 0
    if args.command == "enrol":
        secrets = load_secrets(secrets_path())
        paths = enrol_named(
            data_dir=data_root(),
            kind=args.kind,
            name=args.name,
            sans=list(args.sans),
            password=secrets["STEP_CA_PASSWORD"],
            provisioner=secrets["STEP_PROVISIONER"],
            force=args.force,
        )
        sys.stdout.write(f"root={paths['root']}\ncert={paths['cert']}\nkey={paths['key']}\n")
        return 0
    if args.command == "probe":
        report = probe()
        sys.stdout.write(f"passed={str(report.passed()).lower()} report={report.probes and 'ok'}\n")
        for item in report.probes:
            status = "pass" if item.passed else "fail"
            sys.stdout.write(f"{status} {item.name} {item.detail}\n")
        return 0 if report.passed() else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
