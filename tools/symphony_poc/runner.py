from __future__ import annotations

import argparse
import json

from tools.symphony_poc.controller import SymphonyController


def main() -> int:
    parser = argparse.ArgumentParser(description="Symphony PoC controller")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--task", required=True)

    poll_parser = subparsers.add_parser("poll")
    poll_parser.add_argument("--once", action="store_true")

    args = parser.parse_args()
    controller = SymphonyController()

    if args.command == "run":
        summary = controller.run_task(args.task)
        print(json.dumps(summary, indent=2))
        return 0

    if args.command == "poll":
        if not args.once:
            raise SystemExit("Only --once is supported in the PoC runner.")
        summary = controller.poll_once()
        print(json.dumps(summary, indent=2) if summary else "No queued tasks.")
        return 0

    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
