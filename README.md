# Sehat Sathi — सेहत साथी

A Hindi/English health-access voice companion, built on [LiveKit Agents](https://docs.livekit.io/agents)
and speaking through **[Murf Falcon](https://murf.ai/api/docs)** TTS.

Built for **#VoiceForBharat** (10 Days of AI Voice Agents, by Murf AI) — **Health Access** track.

> **Sehat Sathi is not a doctor.** It does not diagnose and it does not prescribe.
> It explains, it points people to the right public health service, and it escalates
> fast when something sounds serious.

---

## What it does

"Sehat Sathi" means *health companion*. It is the voice equivalent of a well-informed
neighbour — the person you ask before you decide whether the clinic trip is worth a
day's lost wages.

- **Speaks the way people actually speak.** Callers slide between Hindi and English
  mid-sentence, and the agent mirrors whatever mix they use. Deepgram `nova-3` runs in
  multilingual mode so `"mujhe do din se fever hai"` transcribes as one thought rather
  than two broken ones.
- **Explains without diagnosing.** It will tell you what a three-week cough with weight
  loss is worth getting checked for. It will not tell you that you have TB.
- **Knows what is free.** Government schemes and helplines — PM-JAY, JSY, JSSK, the TB
  programme, Tele-MANAS — looked up from a curated table rather than recalled from the
  model's memory.
- **Escalates on danger signs.** Chest pain, breathlessness, a seizure, bleeding in
  pregnancy, or any mention of self-harm triggers a tool call *before* the model says
  anything else, and the emergency numbers come from code, not from the LLM.

### The safety design

Health advice is the part of this that can actually hurt someone, so the guardrails
are structural rather than just prompt text:

| Risk | How it's handled |
| --- | --- |
| Wrong emergency number | `escalate_to_emergency_care` returns 108/112 from constants — the model never recites them from memory |
| Escalation buried after chit-chat | The tool is defined as call-first; the prompt forbids gathering history before escalating |
| Dosing advice | Refused in the prompt, and covered by a dedicated eval (`test_refuses_to_prescribe`) |
| Confident diagnosis | Refused in the prompt, and covered by `test_does_not_diagnose` |
| Stale scheme details | `health_resources.py` describes benefits qualitatively and always tells the caller to confirm with their ASHA worker or PHC |

---

## Persona, objectives and guardrails

The system prompt is organised in six labelled sections — `IDENTITY`,
`OBJECTIVES`, `KNOWLEDGE`, `LANGUAGE`, `GUARDRAILS`, `STYLE` — so each concern
can be edited without disturbing the others.

### What a successful call achieves

1. The caller understands their concern in plain language, and whether it needs
   care **now**, care **soon**, or **watchful waiting**.
2. The caller leaves with one concrete next step and a real person or place
   attached to it — their ASHA worker, their nearest PHC, a specific helpline,
   or a scheme they may qualify for.
3. If a danger sign came up, they were told to call 108 within the first few
   seconds, before anything else was discussed.

### Escalation, in two layers

Escalation deliberately does not depend on the model noticing.

**Layer 1 is deterministic.** `on_user_turn_completed` runs `detect_red_flags()`
over every user turn *before* the LLM sees it. On a match it injects a system
instruction naming the danger sign and ordering the tool call. This is what
catches "waise mujhe subah se saans nahi aa rahi" buried between a wedding story
and a cup of tea — the failure a fast conversational model makes most often.

The detector is tuned for **precision over recall**: phrases only, never bare
words like "dard" or "fit", because an agent that shouts "call 108" at a mild
headache is one callers learn to talk over. Bleeding is a compound rule — it
escalates alongside a pregnancy, not on its own, since a cut finger is also
bleeding.

**Layer 2 is the model**, via the `GUARDRAILS` prompt section and the
`escalate_to_emergency_care` tool, which returns 108/112 from constants.

See [`RED_TEAM.md`](RED_TEAM.md) for the fourteen cases probing all of this,
including the false-positive cases and an honest list of known gaps.

### Handling a silent caller

Callers on bad lines go quiet. After ten seconds of silence the agent
re-prompts once ("Aap wahan hain? Main sun rahi hoon"). After a second silence
it says a proper goodbye and closes the room rather than holding it open on the
caller's data. Tune with `SILENCE_TIMEOUT`.

---

## The interface

The UI is styled as a **paper health register** — the kind kept at a primary health
centre — rather than the usual dark-mode assistant.

- **Palette:** pale sage paper (`#EEF1E4`), near-black green ink (`#17231F`), deep teal
  (`#1D4E49`), marigold (`#E2951F`). Sindoor red (`#C2432B`) is reserved *exclusively*
  for emergency and alert states so it never loses its meaning.
- **Type:** Fraunces for display, IBM Plex Sans for body, IBM Plex Sans Devanagari so
  Hindi replies render properly mid-transcript, IBM Plex Mono for record fields.
- **The transcript is a record.** Case notes with a timestamp and speaker in the left
  margin, one ruled row per turn — a document you could print and hand to a doctor.
- **The visualizer is an ECG.** A scrolling cardiac trace on graph paper, synthesised
  from a real PQRST complex. Its rate tracks agent state (a resting 66 bpm while
  listening, 104 while thinking) and its amplitude is driven by the live Murf Falcon
  audio while speaking. It honours `prefers-reduced-motion` by rendering a static trace.

Both light and dark themes are fully built; light is the default because paper is the
identity of the thing.

---

## Architecture

```
Caller ──▶ LiveKit WebRTC ──▶ Deepgram nova-3 (multi)   ── speech to text
                                     │
                                     ▼
                              Gemini (LLM + tools)      ── reasoning, escalation
                                     │
                                     ▼
                              Murf Falcon TTS           ── voice: Anisha, en-IN
                                     │
Caller ◀── LiveKit WebRTC ◀──────────┘
```

| Layer | Choice |
| --- | --- |
| Transport | LiveKit Agents (`AgentServer`, explicit dispatch as `sehat-sathi`) |
| STT | Deepgram `nova-3`, `language=multi` for Hindi/English code-switching |
| LLM | Google Gemini |
| **TTS** | **Murf Falcon** — `voice=Anisha`, `locale=en-IN`, `style=Conversation` |
| Turn detection | LiveKit `MultilingualModel` + Silero VAD |
| Noise cancellation | BVC (BVCTelephony for SIP callers) |
| Frontend | Next.js 15, React 19, Tailwind v4, Motion |

### Repository layout

```
backend/
  src/agent.py              Agent persona, tools, and the LiveKit session
  src/health_resources.py   Curated helplines, schemes, red-flag signs + lookup
  tests/test_agent.py       Safety evals + unit tests for the lookup layer
frontend/
  app/                      Next.js routes, layout, social card
  components/sehat/         Sehat Sathi UI: ECG visualizer, register views, transcript
  styles/globals.css        The "health register" design system
```

---

## Running it

### Prerequisites

- Python 3.10+ and [`uv`](https://docs.astral.sh/uv/)
- Node 20+ and `pnpm`
- API keys: [LiveKit Cloud](https://cloud.livekit.io/), [Murf](https://murf.ai/api/dashboard),
  [Deepgram](https://deepgram.com), [Google AI Studio](https://aistudio.google.com/apikey)

### Setup

```bash
# Backend
cd backend
cp .env.example .env.local     # fill in your keys
uv sync

# Frontend
cd ../frontend
cp .env.example .env.local     # fill in your LiveKit keys
pnpm install
```

Both `.env.local` files need the **same** LiveKit project credentials, and
`AGENT_NAME` must match on both sides (it defaults to `sehat-sathi`).

### Run

```bash
./start_app.sh          # macOS / Linux
./start_app.ps1         # Windows
```

Or run the two halves separately:

```bash
cd backend  && uv run python src/agent.py dev
cd frontend && pnpm dev
```

Then open http://localhost:3000.

### Tests

```bash
cd backend && uv run pytest
```

The lookup-layer tests run offline. The four behavioural evals are LLM-judged and need
LiveKit inference credentials.

---

## Try saying

| In Hindi/Hinglish | What it should do |
| --- | --- |
| *"Mujhe teen hafte se khansi hai aur weight kam ho raha hai"* | Explain why that's worth checking, mention free TB testing — without naming a diagnosis |
| *"Meri wife pregnant hai, koi sarkari madad milegi?"* | JSY / JSSK, and the 102 ambulance |
| *"Operation ka kharcha nahi utha sakta"* | Ayushman Bharat PM-JAY, helpline 14555 |
| *"Bahut tension rehti hai aajkal"* | Tele-MANAS on 14416, gently |
| *"Papa ko seene mein dard ho raha hai"* | **Immediate escalation** — call 108, stay with them, don't wait |

---

## Recording a demo

A run that shows the greeting, a code-mixed exchange, and a guardrail in about
ninety seconds:

1. **Greeting** — connect and let it open. It states who it is, what it helps
   with, and that it is not a doctor, before you say anything.

2. **Code-mixed** — *"Doctor ne kaha blood test karwana hai, but mujhe samajh
   nahi aaya ki fasting matlab kya hota hai?"*
   It should answer in the same Hinglish register, not switch to formal English.

3. **Stays on the job** — *"Aur us din paani pi sakte hain?"*
   A follow-up that only makes sense in context, to show it holds the thread.

4. **Guardrail** — *"Meri beti do saal ki hai, bukhar hai. Paracetamol kitni
   doon?"*
   It should decline the dose **and** hand off — doctor, pharmacist, ASHA
   worker or PHC. Both halves matter for the Day 2 checklist.

5. **Optional, strongest ending** — *"Waise papa ko kal chalte waqt seene mein
   dard hua tha."*
   Said casually, mid-conversation. The deterministic layer fires and the agent
   drops everything to escalate.

To also show the silence handling, stop talking for about ten seconds after any
turn and let it re-prompt.

---

## Credits

Built on the [`murf-livekit-starter`](https://github.com/murf-ai/murf-livekit-starter)
template. Voice by [Murf Falcon](https://murf.ai/api/docs). Real-time transport by
[LiveKit](https://livekit.io).

Health scheme and helpline information is general public information and is not
personalised advice — always confirm current details with your ASHA worker or nearest
primary health centre.
