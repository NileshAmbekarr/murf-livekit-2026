"""Create the LiveKit outbound SIP trunk the agent dials through.

Run once:

    uv run python scripts/setup_sip_trunk.py            # Linphone (default)
    SIP_PROVIDER=twilio uv run python scripts/setup_sip_trunk.py

It prints a trunk id. Put that in `.env.local` as `SIP_TRUNK_ID`.

A script rather than a thing clicked once in a dashboard, so the setup is
reproducible and the values that matter are visible in one place.

---------------------------------------------------------------------------
Linphone (the default, and free)
---------------------------------------------------------------------------

Twilio's free tier no longer lets a trial account buy a phone number, so
development and demos run over SIP to a softphone instead. The agent dials
`sip:you@sip.linphone.org` and the Linphone app on your handset rings. It is a
real call over a real SIP trunk — just not over the telephone network — which
also means the Indian telemarketing rules do not come into it at all.

  1. Register at https://subscribe.linphone.org/register/email
     You get `sip:<username>@sip.linphone.org`.
  2. Put the username in `.env.local` as `LINPHONE_USERNAME`.
  3. Install the Linphone app, sign in, and allow microphone access.
  4. In the app: Settings > Calls > Advanced call settings >
     turn **Media encryption mandatory OFF**. Calls fail silently otherwise.
  5. Run this script, then `place_calls.py --to <username>`.

No credentials go on the trunk. LiveKit routes the INVITE to sip.linphone.org
over TLS and Linphone rings the registered client.

---------------------------------------------------------------------------
Twilio (if you have a paid account and a real number)
---------------------------------------------------------------------------

  1. Verify the destination under Phone Numbers > Verified Caller IDs.
  2. Buy a number with Voice capability. Buy a **US** one: an Indian number
     needs a regulatory bundle with address proof and takes days.
  3. Elastic SIP Trunking > Trunks > Create:
       Termination      set a SIP URI  ->  gives  something.pstn.twilio.com
       Credential Lists create one     ->  username and password
       Numbers          attach the number from step 2
  4. Set TWILIO_SIP_ADDRESS, TWILIO_SIP_USERNAME, TWILIO_SIP_PASSWORD and
     SIP_CALLER_NUMBER in `.env.local`.

And the thing no configuration fixes: Twilio is not a TRAI-registered
telemarketer in India. Calling your own verified number to build and demo this
is fine; calling real patients this way is not. See the README.
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv
from livekit import api
from livekit.protocol import sip as sip_proto

load_dotenv(".env.local")

TRUNK_NAME = "sehat-sathi-outbound"

LIVEKIT_VARS = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")


def _trunk_for_linphone() -> api.SIPOutboundTrunkInfo:
    """A trunk that reaches Linphone accounts over TLS, with no credentials."""
    username = os.getenv("LINPHONE_USERNAME", "").strip()
    if not username:
        raise SystemExit(
            "Set LINPHONE_USERNAME in .env.local — the username from your\n"
            "sip:<username>@sip.linphone.org address."
        )

    return api.SIPOutboundTrunkInfo(
        name=TRUNK_NAME,
        address="sip.linphone.org",
        transport=sip_proto.SIP_TRANSPORT_TLS,
        # The identity calls appear to come from.
        numbers=[f"sip:{username}"],
    )


def _trunk_for_twilio() -> api.SIPOutboundTrunkInfo:
    required = (
        "TWILIO_SIP_ADDRESS",
        "TWILIO_SIP_USERNAME",
        "TWILIO_SIP_PASSWORD",
        "SIP_CALLER_NUMBER",
    )
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise SystemExit(f"Missing from .env.local: {', '.join(missing)}")

    return api.SIPOutboundTrunkInfo(
        name=TRUNK_NAME,
        address=os.environ["TWILIO_SIP_ADDRESS"],
        numbers=[os.environ["SIP_CALLER_NUMBER"]],
        auth_username=os.environ["TWILIO_SIP_USERNAME"],
        auth_password=os.environ["TWILIO_SIP_PASSWORD"],
    )


async def main() -> int:
    missing = [name for name in LIVEKIT_VARS if not os.getenv(name)]
    if missing:
        print("Missing from .env.local:", ", ".join(missing), file=sys.stderr)
        return 1

    provider = os.getenv("SIP_PROVIDER", "linphone").strip().lower()
    if provider not in ("linphone", "twilio"):
        print(
            f"SIP_PROVIDER must be 'linphone' or 'twilio', not '{provider}'",
            file=sys.stderr,
        )
        return 1

    trunk = _trunk_for_linphone() if provider == "linphone" else _trunk_for_twilio()

    livekit = api.LiveKitAPI()
    try:
        existing = await livekit.sip.list_sip_outbound_trunk(
            api.ListSIPOutboundTrunkRequest()
        )
        for found in existing.items:
            if found.name == TRUNK_NAME:
                print(f"A trunk already exists: {found.sip_trunk_id}")
                print(
                    "Delete it in the LiveKit dashboard first if you want a fresh one."
                )
                return 0

        created = await livekit.sip.create_sip_outbound_trunk(
            api.CreateSIPOutboundTrunkRequest(trunk=trunk)
        )
    finally:
        await livekit.aclose()

    print(f"Created a {provider} trunk, calling out as {trunk.numbers[0]}\n")
    print("Add this to backend/.env.local:\n")
    print(f"    SIP_TRUNK_ID={created.sip_trunk_id}")

    if provider == "linphone":
        print(
            "\nBefore dialling, in the Linphone app:"
            "\n  Settings > Calls > Advanced call settings"
            "\n  > Media encryption mandatory  ->  OFF"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
