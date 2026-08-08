"""Render the same lines across Murf voices, locales and styles, to pick by ear.

Why this exists
---------------
The agent sounded wrong in Hindi and there was no way to compare options without
editing `agent.py`, restarting the worker and phoning it. This renders a matrix
of wav files you can click through in a file browser in about a minute.

What it already told us
-----------------------
`MURF_LOCALE` is sent to Murf as `multiNativeLocale` — "pronounce this text as
this language" — and it was `en-IN` while the agent spoke **romanised** Hindi.
The obvious fix looked like flipping it to `hi-IN`. Measuring says otherwise.

Mean clip length for the same sentence, over 4 voices x 3 styles:

    romanised Hindi     en-IN 9.37s    hi-IN 9.90s
    Devanagari Hindi    en-IN 7.15s    hi-IN 6.93s
    Devanagari+English  en-IN 7.57s    hi-IN 7.59s
    pure English        en-IN 6.49s    hi-IN 6.21s

Two conclusions, both load-bearing. The **script** moves the number by 26-30%
while the **locale** moves it by under 7% — so writing Hindi in Devanagari is
the actual fix, and the locale is close to a rounding error. And flipping the
locale alone would have made things *worse*: romanised Hindi is slower at
`hi-IN` (9.90s) than at `en-IN` (9.37s), because Murf then tries to read Latin
letters as Hindi.

Duration is a proxy — a laboured, letter-by-letter reading takes longer than
fluent speech — so listen before trusting it. But it is consistent across every
voice and style tested.

Because pure English costs nothing at `hi-IN`, one locale serves both languages
and there is no need to switch it per turn.

Usage
-----
    uv run python scripts/audition_voices.py
    uv run python scripts/audition_voices.py --voices Anisha Palak --locales hi-IN
    uv run python scripts/audition_voices.py --out ../audition

Needs `MURF_API_KEY` in `backend/.env.local`, the same as the agent.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import sys
import wave
from pathlib import Path

import aiohttp
from dotenv import load_dotenv
from livekit.plugins import murf

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("audition")

# Run from anywhere: .env.local sits next to the backend package, not the script.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_ROOT / ".env.local")


# The three lines are chosen to expose the failure modes, not to sound nice.
SAMPLES: tuple[tuple[str, str], ...] = (
    # 1. Exactly what the agent says today. This is the accent bug, reproduced.
    (
        "1-romanised",
        "Namaste, main Sehat Sathi hoon. Main aapki sehat ke baare mein "
        "baat karne ke liye hoon. Boliye, kya pareshani hai?",
    ),
    # 2. The same sentence in Devanagari. Compare against 1 at hi-IN.
    (
        "2-devanagari",
        "नमस्ते, मैं सेहत साथी हूँ। मैं आपकी सेहत के बारे में बात करने के लिए हूँ। बोलिए, क्या परेशानी है?",
    ),
    # 3. Code-mixed, because real callers speak this way and the English medical
    #    terms must not come out mangled when the locale is Hindi.
    (
        "3-hinglish",
        "आपका blood pressure check कराना ज़रूरी है। नज़दीकी PHC या ASHA worker "
        "से मिलिए, और report साथ ले जाइए।",
    ),
    # 4. Pure English. The agent must serve English callers too, so this decides
    #    whether the locale has to follow the caller per turn or whether one
    #    setting can serve both languages.
    (
        "4-english",
        "You should get your blood pressure checked. Please visit your nearest "
        "primary health centre, and take your report with you.",
    ),
)

DEFAULT_VOICES = ("Anisha", "Palak", "Pooja", "Nikhil")
DEFAULT_LOCALES = ("en-IN", "hi-IN")
# "Conversation" is what the agent uses today and is the monotone complaint.
DEFAULT_STYLES = ("Conversation", "Conversational", "Calm")


async def render(
    text: str,
    *,
    voice: str,
    locale: str,
    style: str,
    destination: Path,
    http_session: aiohttp.ClientSession,
) -> bool:
    """Synthesise one line and write it as a wav. False if Murf refused."""
    # The plugin borrows the agent worker's http session by default, and there
    # is no worker here, so it has to be handed one explicitly.
    tts = murf.TTS(
        voice=voice,
        locale=locale,
        style=style,
        model="FALCON",
        http_session=http_session,
    )

    try:
        # collect() returns a single combined rtc.AudioFrame, not a wrapper.
        frame = await tts.synthesize(text).collect()
    except Exception as exc:
        # A voice may simply not support a locale or style. That is a useful
        # result, not a crash — report it and keep going through the matrix.
        logger.warning("skipped %s: %s", destination.name, exc)
        return False
    finally:
        with contextlib.suppress(Exception):
            await tts.aclose()

    with wave.open(str(destination), "wb") as out:
        out.setnchannels(frame.num_channels)
        out.setsampwidth(2)  # the plugin only emits pcm_s16le
        out.setframerate(frame.sample_rate)
        out.writeframes(frame.data.tobytes())

    return True


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voices", nargs="+", default=list(DEFAULT_VOICES))
    parser.add_argument("--locales", nargs="+", default=list(DEFAULT_LOCALES))
    parser.add_argument("--styles", nargs="+", default=list(DEFAULT_STYLES))
    parser.add_argument(
        "--out",
        type=Path,
        default=BACKEND_ROOT / "audition",
        help="Directory for the wav files (default: backend/audition).",
    )
    args = parser.parse_args()

    if not os.getenv("MURF_API_KEY"):
        print("MURF_API_KEY is not set. Add it to backend/.env.local.")
        return 1

    args.out.mkdir(parents=True, exist_ok=True)

    combinations = [
        (voice, locale, style)
        for voice in args.voices
        for locale in args.locales
        for style in args.styles
    ]
    total = len(combinations) * len(SAMPLES)
    print(f"Rendering {total} clips into {args.out}\n")

    written = 0
    async with aiohttp.ClientSession() as http_session:
        for voice, locale, style in combinations:
            for label, text in SAMPLES:
                name = f"{voice}-{locale}-{style.replace(' ', '_')}-{label}.wav"
                if await render(
                    text,
                    voice=voice,
                    locale=locale,
                    style=style,
                    destination=args.out / name,
                    http_session=http_session,
                ):
                    written += 1
                    print(f"  {name}")

    print(f"\n{written}/{total} clips written.")
    print(
        "\nListen for two things:\n"
        "  1. Compare -1-romanised against -2-devanagari at hi-IN. If the\n"
        "     romanised one sounds like an English speaker reading Hindi, the\n"
        "     agent's Hindi strings need to move to Devanagari.\n"
        "  2. Check -3-hinglish keeps 'blood pressure' and 'PHC' intelligible\n"
        "     when the locale is hi-IN."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
