"""Place outbound calls — the thing that decides who gets rung, and whether.

    uv run python scripts/place_calls.py --dry-run          # who would be called
    uv run python scripts/place_calls.py --to +919876543210 # ring one number
    uv run python scripts/place_calls.py --reason follow_up # the real run

This script exists to be cautious. Dialling somebody who did not ask to be
dialled is the one thing in this project that can be actively unwelcome, so
every check that can happen before the phone rings happens here:

  * outside 09:00-21:00 IST it refuses to run at all;
  * only callers who agreed to be remembered, agreed *separately* to be called,
    gave a number, and are not on the suppression list;
  * never more than `MAX_ATTEMPTS` times for one reason;
  * `--dry-run` first, always.

The agent does the dialling itself — the job metadata carries the number, and
`sehat_sathi()` calls `create_sip_participant`. That way the agent is already in
the room when the phone is answered, instead of joining a moment later while
somebody says "hello? hello?".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from livekit import api

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory import InvalidPhoneError, MemoryStore, normalise_phone
from outbound import (
    IST,
    MAX_ATTEMPTS,
    Outcome,
    Reason,
    deserves_follow_up,
    next_attempt,
    next_window_opens,
    outcome_from_sip_status,
    within_calling_window,
)

load_dotenv(".env.local")

AGENT_NAME = "sehat-sathi"


def _sip_status_of(error: Exception) -> int | None:
    """Dig the SIP response code out of whatever LiveKit raised.

    The status arrives in the error text rather than as a field, so this is
    deliberately forgiving: an unrecognised failure becomes `FAILED`, which
    retries, rather than being mistaken for a decline, which would not.
    """
    text = str(error)
    for code in (486, 600, 487, 480, 603, 607, 608):
        if str(code) in text:
            return code
    return None


async def place_one(
    livekit: api.LiveKitAPI, *, phone: str, reason: str, caller_id: str = ""
) -> Outcome:
    """Dispatch the agent to ring one number, and report how it went."""
    metadata = json.dumps({"phone": phone, "reason": reason, "caller_id": caller_id})

    try:
        await livekit.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=f"outbound-{reason}-{int(datetime.now().timestamp())}",
                metadata=metadata,
            )
        )
    except Exception as error:
        status = _sip_status_of(error)
        outcome = outcome_from_sip_status(status)
        print(f"  {phone}: {outcome.value} (sip {status or 'unknown'})")
        return outcome

    print(f"  {phone}: dispatched")
    return Outcome.ANSWERED


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reason", default=Reason.FOLLOW_UP.value, choices=[r.value for r in Reason]
    )
    parser.add_argument(
        "--to",
        help=(
            "Ring one destination and skip the caller list entirely. Either a "
            "phone number (+919876543210) or a Linphone username."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="List who would be called"
    )
    parser.add_argument(
        "--ignore-window",
        action="store_true",
        help="Call outside 09:00-21:00 IST. For testing your own phone only.",
    )
    args = parser.parse_args()

    now = datetime.now(IST)
    if not within_calling_window(now) and not args.ignore_window:
        print(
            f"It is {now:%H:%M} IST. Calling is only allowed between 09:00 and 21:00 "
            f"— next window opens {next_window_opens(now):%a %H:%M}.",
            file=sys.stderr,
        )
        print("Use --ignore-window only for your own phone.", file=sys.stderr)
        return 1

    # One-off dial, for testing against your own handset.
    if args.to:
        store = MemoryStore(os.getenv("MEMORY_DB_PATH", "data/callers.db"))
        try:
            # Turns a bare Linphone username into sip:user@sip.linphone.org, and
            # rejects anything that is not somewhere we can actually call.
            args.to = normalise_phone(args.to)
        except InvalidPhoneError as bad:
            print(bad, file=sys.stderr)
            return 1
        if store.is_do_not_call(args.to):
            print(f"{args.to} has opted out. Refusing.", file=sys.stderr)
            return 1
        if args.dry_run:
            print(f"Would call {args.to} with reason '{args.reason}'.")
            return 0

        livekit = api.LiveKitAPI()
        try:
            await place_one(livekit, phone=args.to, reason=args.reason)
        finally:
            await livekit.aclose()
        return 0

    store = MemoryStore(os.getenv("MEMORY_DB_PATH", "data/callers.db"))
    due = store.callers_to_ring(reason=args.reason, max_attempts=MAX_ATTEMPTS)

    # A follow-up is only for people whose last call ended in advice to seek
    # care. Notably not an emergency referral — see `outbound.FOLLOW_UP_OUTCOMES`.
    if args.reason == Reason.FOLLOW_UP.value:
        due = [
            c for c in due if deserves_follow_up(c.facts.get("last_triage_outcome", ""))
        ]

    if not due:
        print(f"Nobody is due a '{args.reason}' call.")
        return 0

    print(f"{len(due)} caller(s) due a '{args.reason}' call:")
    for caller in due:
        attempts = caller.call_attempts.get(args.reason, 0)
        print(
            f"  {caller.name or '(unnamed)'} — attempts so far: {attempts}"
            f" — last outcome: {caller.facts.get('last_triage_outcome', 'n/a')}"
        )

    if args.dry_run:
        print("\nDry run: nothing was dialled.")
        return 0

    livekit = api.LiveKitAPI()
    try:
        for caller in due:
            outcome = await place_one(
                livekit,
                phone=caller.phone,
                reason=args.reason,
                caller_id=caller.user_id,
            )
            attempts = store.record_call_attempt(
                caller.user_id, reason=args.reason, outcome=outcome.value
            )
            rule = next_attempt(outcome, attempts)
            print(
                f"    -> {'retry in ' + str(rule.wait) if rule.retry else 'no retry'}: {rule.why}"
            )
    finally:
        await livekit.aclose()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
