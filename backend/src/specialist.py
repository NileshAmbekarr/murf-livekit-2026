"""Yojana Sathi — Government health schemes and entitlements specialist agent.

A focused specialist agent that handles detailed questions about Indian central
and state government health schemes (Ayushman Bharat / PM-JAY, Janani Suraksha Yojana,
Janani Shishu Suraksha Karyakram, Pradhan Mantri Matru Vandana Yojana, Nikshay Poshan Yojana,
ABHA card, state health cards, required documents, and eligibility).

When off-topic queries (medical symptoms, clinic lookups, emergency signs) arise,
Yojana Sathi hands the conversation back to Sehat Sathi.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from livekit.agents import (
    Agent,
    ChatContext,
    RunContext,
    function_tool,
    tokenize,
)
from livekit.plugins import murf

from health_resources import find_helplines, find_schemes

if TYPE_CHECKING:
    pass

logger = logging.getLogger("yojana-sathi")

YOJANA_PROMPT = """
# IDENTITY
You are Yojana Sathi (योजना साथी), a government health schemes and entitlements
specialist working alongside Sehat Sathi. You are knowledgeable, warm, and
dedicated to helping citizens understand government health schemes across India.

# OBJECTIVES
Your sole job is to help callers navigate government health schemes and entitlements:
1. Explain eligibility criteria, benefits, coverage limits, and application processes
   for central and state schemes (e.g. Ayushman Bharat PM-JAY, Janani Suraksha Yojana,
   JSSK, PMMVY, Nikshay Poshan Yojana for TB, ABHA ID card, and state health schemes).
2. Detail required documents (Aadhaar card, Ration card / BPL card, bank passbook,
   mobile number linked with Aadhaar, birth certificate where relevant).
3. Guide callers on WHERE to go for enrollment (nearest Common Service Centre / CSC,
   Gram Panchayat, ASHA didi, empanelled hospital kiosk, or government portal).
4. For PM-JAY questions, remind them they can check their name and eligibility
   on the official portal or by calling 14555.

# BOUNDARIES & HAND-BACK
You are a scheme specialist, NOT a medical doctor.
- Do NOT diagnose symptoms, prescribe medications, or provide medical triage.
- If the caller asks about health symptoms, finding a nearby clinic/PHC/hospital,
  needs human help escalation, or mentions any emergency / danger signs
  (e.g., chest pain, difficulty breathing, severe bleeding), you MUST call the
  `transfer_back_to_sehat_sathi` tool immediately!
- If the conversation moves entirely away from government schemes to general health,
  politely transfer back to Sehat Sathi using `transfer_back_to_sehat_sathi`.

# LANGUAGE & SCRIPT
You speak Hindi and English in whatever mix the caller uses.

## Script Rule — Devanagari only for Hindi
Write all spoken Hindi in Devanagari script (देवनागरी). Never write Hindi in
Latin/English letters (write "नमस्ते", never "namaste").
Common English terms (such as "card", "portal", "CSC centre", "online", "Aadhaar",
"hospital", "cashless") can stay in English or Devanagari.

# STYLE
- Keep sentences short, simple and conversational (under ~20 words per sentence).
- Never use markdown formatting (no bold **, bullet points *, numbered lists 1., or headings #).
  Your responses are read aloud by TTS.
- Explain scheme benefits qualitatively and remind callers to confirm state-specific
  rules with their ASHA didi or nearest CSC centre.
""".strip()


class YojanaSathi(Agent):
    """The Yojana Sathi specialist persona, focused on government health schemes."""

    def __init__(
        self,
        caller_id: str = "",
        chat_ctx: ChatContext | None = None,
        tts: murf.TTS | None = None,
    ) -> None:
        if tts is None:
            tts = murf.TTS(
                voice=os.getenv("YOJANA_MURF_VOICE_ID", "Khyati"),
                locale=os.getenv("MURF_LOCALE", "hi-IN"),
                style=os.getenv("YOJANA_MURF_STYLE", "Conversational"),
                model="FALCON",
                tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                text_pacing=True,
            )
        super().__init__(
            instructions=YOJANA_PROMPT,
            chat_ctx=chat_ctx,
            tts=tts,
        )
        self._caller_id = caller_id

    async def on_enter(self) -> None:
        """Called when Yojana Sathi takes over the conversation."""
        logger.info(
            "Yojana Sathi entered conversation",
            extra={"caller_id": self._caller_id},
        )
        await self.session.generate_reply(
            instructions=(
                "Introduce yourself in Devanagari Hindi as Yojana Sathi (योजना साथी), "
                "the government health scheme specialist. Acknowledge that you are here "
                "to help with health schemes, Ayushman Bharat card, maternity benefits, "
                "or document requirements, and ask how you can help."
            )
        )

    @function_tool()
    async def find_health_service(self, context: RunContext, topic: str) -> str:
        """Look up government health programmes, schemes and national helplines by topic.

        Args:
            topic: What the caller needs help with, e.g. "Ayushman Bharat",
                "PM-JAY card", "maternity benefit", "Janani Suraksha",
                "TB treatment", "ABHA card".
        """
        logger.info("Yojana Sathi health service lookup", extra={"topic": topic})

        helplines = find_helplines(topic)
        schemes = find_schemes(topic)

        if not helplines and not schemes:
            return (
                "No specific match. Tell the caller their nearest Common Service Centre (CSC) "
                "or their ASHA worker is the right first stop, and the Ayushman helpline is 14555."
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
            + "\n\nShare the most relevant details clearly. Remind them to confirm details with "
            "their ASHA worker or local CSC centre, as specific rules may vary."
        )

    @function_tool()
    async def transfer_back_to_sehat_sathi(
        self, context: RunContext
    ) -> tuple[Agent, str]:
        """Transfer the caller back to Sehat Sathi.

        Use this tool when the caller asks about health symptoms, medical conditions,
        finding a nearby hospital/clinic/PHC, emergency assistance, or anything
        outside government health schemes and entitlements.
        """
        from agent import SehatSathi

        logger.info(
            "Handing back conversation to Sehat Sathi",
            extra={"caller_id": self._caller_id},
        )
        sehat_agent = SehatSathi(
            caller_id=self._caller_id,
            chat_ctx=self.chat_ctx.copy(exclude_instructions=True),
            is_transfer=True,
        )
        return (
            sehat_agent,
            "स्वास्थ्य संबंधी अन्य सवालों के लिए, मैं आपको वापस सेहत साथी से जोड़ रही हूँ।",
        )
