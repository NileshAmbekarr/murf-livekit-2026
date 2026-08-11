"""Create the LiveKit outbound SIP trunk that points at Twilio.

Run once, after the Twilio side is set up:

    uv run python scripts/setup_sip_trunk.py

It prints a trunk id. Put that in `.env.local` as `SIP_TRUNK_ID`.

A script rather than a thing clicked once in a dashboard, so the setup is
reproducible and reviewable — and so the next person can see exactly which
Twilio values matter.

What Twilio needs first (console.twilio.com):

  1. Verify your own mobile under Phone Numbers > Verified Caller IDs. Trial
     accounts can only dial verified numbers, so without this nothing rings.
  2. Buy a number with Voice capability. Buy a **US** one: an Indian number
     needs a regulatory bundle with address proof and takes days.
  3. Elastic SIP Trunking > Trunks > Create:
       Termination      set a SIP URI  ->  gives  something.pstn.twilio.com
       Credential Lists create one     ->  username and password
       Numbers          attach the number from step 2

Then set in `.env.local`:

    TWILIO_SIP_ADDRESS=something.pstn.twilio.com
    TWILIO_SIP_USERNAME=...
    TWILIO_SIP_PASSWORD=...
    SIP_CALLER_NUMBER=+1XXXXXXXXXX

A reminder that no amount of configuration fixes: Twilio is not a TRAI-registered
telemarketer in India. Calling your own verified phone to build and demo this is
fine. Calling real patients this way is not — that needs an Indian registered
provider. See the README.
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv
from livekit import api

load_dotenv(".env.local")

REQUIRED = (
    "TWILIO_SIP_ADDRESS",
    "TWILIO_SIP_USERNAME",
    "TWILIO_SIP_PASSWORD",
    "SIP_CALLER_NUMBER",
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
)


async def main() -> int:
    missing = [name for name in REQUIRED if not os.getenv(name)]
    if missing:
        print("Missing from .env.local:", ", ".join(missing), file=sys.stderr)
        print("\nSee the docstring at the top of this file for the Twilio steps.")
        return 1

    caller_number = os.environ["SIP_CALLER_NUMBER"]

    livekit = api.LiveKitAPI()
    try:
        existing = await livekit.sip.list_sip_outbound_trunk(
            api.ListSIPOutboundTrunkRequest()
        )
        for trunk in existing.items:
            if trunk.name == "sehat-sathi-outbound":
                print(f"A trunk already exists: {trunk.sip_trunk_id}")
                print(
                    "Delete it in the LiveKit dashboard first if you want a fresh one."
                )
                return 0

        created = await livekit.sip.create_sip_outbound_trunk(
            api.CreateSIPOutboundTrunkRequest(
                trunk=api.SIPOutboundTrunkInfo(
                    name="sehat-sathi-outbound",
                    address=os.environ["TWILIO_SIP_ADDRESS"],
                    numbers=[caller_number],
                    auth_username=os.environ["TWILIO_SIP_USERNAME"],
                    auth_password=os.environ["TWILIO_SIP_PASSWORD"],
                )
            )
        )
    finally:
        await livekit.aclose()

    print(f"Created trunk, calling out from {caller_number}\n")
    print("Add this to backend/.env.local:\n")
    print(f"    SIP_TRUNK_ID={created.sip_trunk_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
