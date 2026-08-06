"""Sehat Sathi — a Hindi/English health-access voice companion.

Built for the #VoiceForBharat challenge (Health Access track) on LiveKit Agents,
speaking through Murf Falcon TTS.

Sehat Sathi is deliberately *not* a diagnosis engine. It is the voice equivalent
of a well-informed neighbour: it listens in whatever mix of Hindi and English
the caller is comfortable with, explains what public health services exist, and
gets people to a real human — an ASHA worker, a PHC, or an ambulance — quickly
when that is what the situation needs.
"""

import logging
import os

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
    room_io,
    tokenize,
)
from livekit.plugins import deepgram, google, murf, noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from health_resources import (
    EMERGENCY_AMBULANCE,
    NATIONAL_EMERGENCY,
    RED_FLAG_SIGNS,
    find_helplines,
    find_schemes,
)

logger = logging.getLogger("sehat-sathi")

load_dotenv(".env.local")

AGENT_NAME = "sehat-sathi"

# --- Model configuration -----------------------------------------------------
# Pinned to values verified against the Murf Voice Library and Google AI Studio,
# but overridable from .env.local so a demo can be re-voiced without a code change.
MURF_VOICE = os.getenv("MURF_VOICE_ID", "Anisha")
MURF_LOCALE = os.getenv("MURF_LOCALE", "en-IN")
MURF_STYLE = os.getenv("MURF_STYLE", "Conversation")
LLM_MODEL = os.getenv("GOOGLE_LLM_MODEL", "gemini-3.5-flash-lite")

# Deepgram nova-3 in multilingual mode is what lets a caller slide between Hindi
# and English mid-sentence ("mujhe do din se fever hai"), which is how people
# actually speak. Set DEEPGRAM_LANGUAGE=en to fall back to English-only.
STT_LANGUAGE = os.getenv("DEEPGRAM_LANGUAGE", "multi")


SYSTEM_PROMPT = f"""
You are Sehat Sathi, a warm health companion for people across India. Your name
means "health companion" and that is exactly what you are — a knowledgeable
friend, never a doctor.

# Language
Speak naturally in the language the caller uses. Most callers mix Hindi and
English, so mirror their mix rather than correcting it. If they speak only
Hindi, reply in simple Hindi. If they speak only English, reply in Indian
English. Use "aap", never "tum". Keep the register warm and respectful, the way
a good ASHA didi speaks — never clinical, never condescending.

# What you are for
- Explaining what a symptom or condition generally means in plain language.
- Telling people which government health service, scheme or helpline can help
  them, and what to carry when they go.
- Preventive basics: nutrition, hydration, hygiene, vaccination schedules,
  antenatal check-ups, medication adherence.
- Preparing someone for a clinic visit: what to describe to the doctor, what
  questions to ask.

# What you must never do
- Never diagnose. Do not name a specific disease as the caller's condition.
  Say what the symptoms *could* relate to, and that only an examination can tell.
- Never prescribe. Do not name a specific medicine, dose, or duration, and do
  not tell anyone to start, stop or change a medicine. Doses in particular can
  kill; refuse them every time, gently.
- Never suggest home remedies as a substitute for care for anything serious.
- Never claim a symptom is definitely harmless.
- Never ask for or repeat back identifying details: no Aadhaar, no full address,
  no bank information. If a caller offers them, tell them they do not need to
  share that with you.

# Escalation — this is the most important part of your job
If the caller mentions any danger sign, stop everything else and use the
`escalate_to_emergency_care` tool immediately, before continuing the
conversation. Danger signs include: {"; ".join(RED_FLAG_SIGNS)}.
Do not gather more history first. Do not reassure first. Escalate, then stay on
the line and keep them calm.

For anything persistent, worsening, or involving a pregnancy, a newborn, or an
elderly person, direct them to their ASHA worker or nearest PHC even if it is
not an emergency.

# Tools
- `escalate_to_emergency_care` — for danger signs. Gives you the exact numbers.
- `find_health_service` — for helplines and government schemes. Use it rather
  than reciting numbers from memory, so the caller gets current information.

# How you speak
Your words are converted to speech, so write for the ear:
- Two or three short sentences per turn. Never monologue.
- No markdown, no bullet points, no emoji, no asterisks, no numbered lists.
- Say numbers as words the way a person would: "one zero eight", not "108".
- Ask one question at a time, then wait.
- If you do not know something, say so plainly and point them to a human.

Open by asking how they are feeling today and what you can help with.
""".strip()


class SehatSathi(Agent):
    """The Sehat Sathi persona, with its escalation and lookup tools."""

    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)

    @function_tool
    async def escalate_to_emergency_care(
        self,
        context: RunContext,
        danger_sign: str,
        is_pregnancy_related: bool = False,
    ) -> str:
        """Use IMMEDIATELY when the caller describes a medical danger sign.

        Call this before asking any follow-up questions. It returns the exact
        emergency guidance to deliver. Examples of when to call it: chest pain,
        breathlessness, fainting, a seizure, uncontrolled bleeding, slurred
        speech or a drooping face, a serious injury, a newborn who will not
        feed, bleeding during pregnancy, or any mention of self-harm.

        Args:
            danger_sign: What the caller described, in their own words.
            is_pregnancy_related: True if the caller is pregnant or has a newborn.
        """
        logger.warning(
            "emergency escalation triggered",
            extra={"danger_sign": danger_sign, "pregnancy": is_pregnancy_related},
        )

        maternal_line = (
            " For a pregnancy or a newborn they can also call one zero two, which "
            "is the free ambulance for mothers and babies."
            if is_pregnancy_related
            else ""
        )

        return (
            "EMERGENCY. Deliver this now, calmly, in the caller's language, in "
            "short sentences.\n"
            f"1. Tell them to call {EMERGENCY_AMBULANCE} for an ambulance right "
            f"now, or {NATIONAL_EMERGENCY} if that does not connect. Say the "
            "digits as words.\n"
            f"{maternal_line}\n"
            "2. Tell them to get someone nearby to stay with the patient.\n"
            "3. Tell them not to wait to see if it improves on its own, and not "
            "to drive themselves.\n"
            "4. Say you will stay with them, and ask if someone is with them.\n"
            "Do not diagnose. Do not suggest any medicine. Do not offer home "
            "remedies. Keep every sentence short."
        )

    @function_tool
    async def find_health_service(self, context: RunContext, topic: str) -> str:
        """Look up Indian health helplines and government schemes for a topic.

        Use this whenever the caller asks where to go, what help exists, whether
        something is free, or how to afford treatment.

        Args:
            topic: What the caller needs help with, e.g. "pregnancy", "TB
                treatment", "cost of an operation", "child vaccination",
                "feeling depressed".
        """
        logger.info("health service lookup", extra={"topic": topic})

        helplines = find_helplines(topic)
        schemes = find_schemes(topic)

        if not helplines and not schemes:
            return (
                "No specific match. Tell the caller their nearest primary health "
                "centre or their ASHA worker is the right first stop, and that "
                "the national health helpline is one zero seven five."
            )

        parts: list[str] = []
        for helpline in helplines:
            parts.append(
                f"Helpline {helpline.number} — {helpline.name}. {helpline.detail}"
            )
        for scheme in schemes:
            parts.append(
                f"Scheme: {scheme.name}. {scheme.summary} Where: {scheme.where}"
            )

        return (
            "\n".join(parts)
            + "\n\nShare at most two of these, whichever fit best. Say phone "
            "numbers as separate words. Remind them to confirm details with "
            "their ASHA worker or PHC, since schemes vary by state."
        )


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name=AGENT_NAME)
async def sehat_sathi(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    session = AgentSession(
        # Ears — nova-3 in multilingual mode handles Hindi/English code-switching.
        stt=deepgram.STT(model="nova-3", language=STT_LANGUAGE),
        # Brain
        llm=google.LLM(model=LLM_MODEL),
        # Voice — Murf Falcon, the fastest TTS API.
        tts=murf.TTS(
            voice=MURF_VOICE,
            locale=MURF_LOCALE,
            style=MURF_STYLE,
            model="FALCON",
            # Short sentence chunks keep first-audio latency low, which matters a
            # lot on the 3G connections this agent is meant to work over.
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    await session.start(
        agent=SehatSathi(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind
                    == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )

    await ctx.connect()

    # A fixed opening line rather than a generated one: it makes the first thing
    # a caller hears predictable, and it sets the Hindi/English tone immediately.
    await session.say(
        "Namaste, main Sehat Sathi hoon. Aap apni sehat ke baare mein kuch bhi "
        "pooch sakte hain. Aaj aap kaisa mehsoos kar rahe hain?"
    )


if __name__ == "__main__":
    cli.run_app(server)
