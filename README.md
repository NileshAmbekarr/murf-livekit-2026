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

## Credits

Built on the [`murf-livekit-starter`](https://github.com/murf-ai/murf-livekit-starter)
template. Voice by [Murf Falcon](https://murf.ai/api/docs). Real-time transport by
[LiveKit](https://livekit.io).

Health scheme and helpline information is general public information and is not
personalised advice — always confirm current details with your ASHA worker or nearest
primary health centre.
