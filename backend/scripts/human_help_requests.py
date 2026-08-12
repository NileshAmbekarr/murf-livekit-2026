"""Review and update the local Day 7 human-help queue.

    uv run python scripts/human_help_requests.py
    uv run python scripts/human_help_requests.py --status open
    uv run python scripts/human_help_requests.py --set-status SS-20260812-ABC123 in_progress

This is deliberately an operator-only development utility. It lets the demo
show that a request is durable and can move through open, in progress, and
resolved without exposing health requests through an unauthenticated webpage.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

load_dotenv(".env.local")


def _when(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )


def main() -> int:
    # Imported after `src` is added to the script's import path above.
    from human_help import HumanHelpStore, REQUEST_STATUSES  # isort: skip

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status", choices=REQUEST_STATUSES, help="Only show this status"
    )
    parser.add_argument(
        "--set-status",
        nargs=2,
        metavar=("REFERENCE", "STATUS"),
        help="Set one request to open, in_progress, or resolved.",
    )
    args = parser.parse_args()

    store = HumanHelpStore(
        os.getenv("HUMAN_HELP_DB_PATH", "data/human_help_requests.db")
    )
    if args.set_status:
        reference, status = args.set_status
        if status not in REQUEST_STATUSES:
            parser.error(f"STATUS must be one of: {', '.join(REQUEST_STATUSES)}")
        request = store.update_status(reference, status)
        if request is None:
            print(f"No request found for {reference}.", file=sys.stderr)
            return 1
        print(f"{request.reference_id} is now {request.status}.")
        return 0

    requests = store.list_requests(args.status or "")
    if not requests:
        print("No human-help requests found.")
        return 0

    for request in requests:
        print(
            f"{request.reference_id} | {request.status} | {request.urgency} | "
            f"{request.reason} | email {request.notification_status} | "
            f"{_when(request.updated_at)}"
        )
        print(f"  {request.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
