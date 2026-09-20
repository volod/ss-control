"""Command line for the site-control evaluation."""

import argparse
import logging
import sys

from ss_control.eval.models import CANDIDATES
from ss_control.eval.runner import down_all, run_eval


def main(argv: list[str] | None = None) -> int:
    """Run or tear down the evaluation."""
    parser = argparse.ArgumentParser(prog="ss-control-eval")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="start each candidate, probe, sample docker stats")
    run.add_argument(
        "--candidate",
        action="append",
        dest="candidates",
        help="candidate id (repeatable); default is all",
    )
    run.add_argument(
        "--skip-cadence", action="store_true", help="do not fetch GitHub release pages"
    )
    sub.add_parser("down", help="stop leftover evaluation compose projects")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "down":
        down_all()
        return 0
    wanted = args.candidates
    selected = CANDIDATES
    if wanted:
        known = {item.id: item for item in CANDIDATES}
        missing = [name for name in wanted if name not in known]
        if missing:
            parser.error("unknown candidate: " + ", ".join(missing))
        selected = tuple(known[name] for name in wanted)
    path = run_eval(candidates=selected, skip_cadence=args.skip_cadence)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
