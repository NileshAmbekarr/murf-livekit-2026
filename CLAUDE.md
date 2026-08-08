# Sehat Sathi — working context

Handoff notes for continuing development. Read this before changing anything in
`backend/src/agent.py` or `frontend/components/sehat/`.

**What this is:** a Hindi/English health-access voice agent built for
**#VoiceForBharat** (10 Days of AI Voice Agents, by Murf AI), on LiveKit Agents
with **Murf Falcon** TTS.

**Where things stand:** Days 1 and 2 are done and posted. Branch
`claude/sehat-sathi-agent-ydr4cm`, open as PR #1 against `main`.

---

## Locked decisions

These are settled. Changing them means redoing published work.

| | Choice | Note |
|---|---|---|
| Track | **Health Access** | Locked after Day 3 by challenge rules |
| Voice | Murf Falcon, `Anisha`, `en-IN`, style `Conversation` | Pinned and verified working |
| LLM | Google Gemini (`gemini-3.5-flash-lite`) | `GOOGLE_API_KEY` |
| STT | Deepgram `nova-3`, `language=multi` | The `multi` setting is what enables code-switching |
| Agent name | `sehat-sathi` | Must match in backend `AGENT_NAME` and frontend `app-config.ts` |
| Design | Paper health register — sage/ink/teal/marigold | Not the stock LiveKit dark theme |

Model and voice settings are env-overridable (`MURF_VOICE_ID`, `MURF_LOCALE`,
`MURF_STYLE`, `GOOGLE_LLM_MODEL`, `DEEPGRAM_LANGUAGE`) so a demo can be re-voiced
without touching code.

---

## The one thing to understand first

**Escalation is layered, and the two layers are not interchangeable.**

**Layer 1 — deterministic, in code.** `SehatSathi.on_user_turn_completed`
(`backend/src/agent.py`) runs `detect_red_flags()` over every user turn *before
the LLM sees it*. On a match it injects a system message naming the danger sign
and ordering the tool call. No model judgement involved.

**Layer 2 — the model.** The `GUARDRAILS` prompt section plus the
`escalate_to_emergency_care` tool, which returns 108/112 from constants in
`health_resources.py` so they can never be hallucinated.

Layer 1 exists because layer 2 demonstrably fails: asked about chest pain buried
in small talk, the model asked triage questions instead of escalating. That is
documented in `RED_TEAM.md`.

### Tuning rule for the detector

`RED_FLAG_PHRASES` is tuned for **precision over recall**, deliberately.

- Phrases only, never bare words. `"dard"` and `"fit"` alone would fire on half
  of all normal conversation.
- An agent that shouts "call one zero eight" at a mild headache is one callers
  learn to talk over — and then the alarm is worthless on the day it matters.
- Bleeding is a **compound rule**: it escalates alongside a pregnancy, not on
  its own, because a cut finger is also bleeding.

If you add phrases, add a matching negative case to
`TestDeterministicLayer::test_ordinary_complaints_do_not_escalate`. False
positives are treated as bugs of equal severity to misses here.

### The false-alarm brake

`escalate_to_emergency_care` checks its own input. If the description contains
**no known danger sign** *and* describes something running **a week or more**,
it refuses to return the emergency script and returns calm-referral instructions
instead.

It checks `detect_red_flags` first, so a genuine danger sign is never suppressed
however long it has been going on. It only knows durations of a week or more —
never "two days" — because two days of breathlessness can absolutely be an
emergency. Keep it conservative.

---

## Bugs already found and fixed — do not reintroduce

All three came out of the first live red-team run. Full write-up in
`RED_TEAM.md`.

**1. Crying wolf.** A three-week cough got escalated to "call an ambulance".
Root cause was a prompt line written to be cautious — *"if you are unsure
whether something counts, treat it as a danger sign"* — which the model read as
permission to over-trigger. If you ever feel like adding that line back, don't.
The `## What is NOT an emergency` prompt section is what replaced it.

**2. Wrong ambulance number, in Tamil.** Given Tamil input the agent replied in
Tamil and spoke 108 as "nine, zero". The language limit lost to the escalation
instruction, which said to deliver the script "in the caller's language". Both
the `LANGUAGE` section and `ESCALATION_SCRIPT` now say Hindi/English only, and
`ESCALATION_SCRIPT` states the reasoning explicitly. **Keep those two in
agreement** — that contradiction is what caused the bug.

**3. A test that couldn't pass.** See the harness gotcha below.

---

## Gotchas that cost time

- **`session.run()` does not call `on_user_turn_completed`.** It goes
  `generate_reply()` → `_pipeline_reply_task()` directly. The hook only fires
  from `on_end_of_turn()` on the *voice* path. So layer 1 is invisible to the
  test harness. Test it directly (`TestTurnHook` in `tests/test_red_team.py`),
  or seed the injected instruction with `agent.update_chat_ctx()` before
  `session.run()` — `test_rt13_escalates_when_layer_one_has_fired` shows the
  pattern.
- **Next.js ignores `app/` folders starting with `_`.** A route at
  `app/__preview/` silently 404s. Name scratch routes without the underscore.
- **`AGENT_NAME` must match on both sides.** Backend registers under it,
  frontend dispatches to it. A mismatch connects but the agent never speaks —
  the single most common "it's broken" cause.
- **Both `.env.local` files need the *same* LiveKit project.** Same failure mode
  as above.
- **The evals run on LiveKit Cloud inference**, authenticated with the same
  `LIVEKIT_API_KEY`/`SECRET`. No separate OpenAI key needed despite the model id
  saying `openai/gpt-4.1-mini`.
- **`prefers-reduced-motion` is honoured by the ECG canvas** — if you touch the
  render loop, keep the static-trace branch working.

---

## File map

Only the files that carry real decisions.

```
backend/src/
  agent.py              Persona, prompt, tools, turn hook, silence handling,
                        LiveKit session wiring. Single entrypoint.
  health_resources.py   Helplines, schemes, red-flag phrases, matching logic.
                        Pure functions, no LiveKit imports — fast to test.
backend/tests/
  test_agent.py         Safety evals + code-mixed language + lookup unit tests
  test_red_team.py      14 adversarial cases, layer-1 hook tests, regressions

frontend/
  app-config.ts               Branding, agentName, feature flags
  app/layout.tsx              Fonts, masthead, theme provider
  styles/globals.css          THE design system — palette, type, .register-card,
                              .paper-rules, .record-field, .field-label
  components/sehat/
    ecg-visualizer.tsx        Canvas PQRST trace. The signature element.
    session-view.tsx          Live consultation view
    welcome-view.tsx          Intake card
    record-transcript.tsx     Case-notes transcript
    agent-status.ts           Bilingual state labels, elapsed-time format

RED_TEAM.md             Adversarial results + the three findings + known gaps
README.md               Setup, architecture, demo script
```

`frontend/components/agents-ui/` and `components/ui/` are upstream
LiveKit/shadcn components. They are driven by the CSS tokens — restyle via
`globals.css` rather than editing them, so `pnpm shadcn:install` stays usable.

---

## Design system

Defined once in `frontend/styles/globals.css`. Do not hardcode colours in
components; use the tokens.

| Token | Light | Meaning |
|---|---|---|
| `--background` | `#EEF1E4` | Pale sage paper |
| `--foreground` | `#17231F` | Near-black green ink |
| `--card` | `#F6F8EF` | A fresh sheet |
| `--primary` / `--teal` | `#1D4E49` | Deep teal, the "stamp" colour |
| `--marigold` | `#E2951F` | Accent only — highlights, active markers |
| `--sindoor` | `#C2432B` | **Emergencies and alerts ONLY** |
| `--rule` | `#C9CDB8` | Ledger line |

**The sindoor rule is a real constraint, not decoration.** If red starts
appearing on ordinary UI, it stops meaning "emergency" — the same cry-wolf logic
as the escalation detector.

Type: Fraunces (display) / IBM Plex Sans (body) / IBM Plex Sans Devanagari
(Hindi — loaded separately so Hindi replies don't fall back mid-transcript) /
IBM Plex Mono (record fields).

Light is the default theme on purpose: paper is the identity. Dark is fully
built and must keep working.

---

## Running it

```bash
# Backend
cd backend && cp .env.example .env.local && uv sync
uv run python src/agent.py download-files   # first time only
uv run python src/agent.py dev
uv run python src/agent.py console          # terminal-only, no frontend

# Frontend
cd frontend && cp .env.example .env.local && pnpm install && pnpm dev

# Both
./start_app.sh     # or start_app.ps1 on Windows
```

**Keys:** LiveKit (cloud.livekit.io) · Murf (murf.ai/api/dashboard) · Deepgram
(console.deepgram.com) · Google AI Studio (aistudio.google.com/apikey).
Backend needs all four; frontend needs only the three LiveKit values plus
`AGENT_NAME`.

### Tests

45 tests. 29 run offline; the rest are LLM-judged and need LiveKit creds.

```bash
cd backend
uv run pytest                                          # everything
uv run pytest -k "Deterministic or TurnHook or lookup"  # offline only, ~4s
uvx ruff check src tests && uvx ruff format src tests
```

```bash
cd frontend
pnpm lint && npx tsc --noEmit && pnpm build
```

Run the offline set on every change to `health_resources.py` — it's fast and
covers the safety-critical matching.

---

## Conventions

- **Branch:** `claude/sehat-sathi-agent-ydr4cm`. PR #1 tracks it.
- **No AI attribution** in commits or PRs — no `Co-Authored-By`, no generated-by
  footer. The user asked for this explicitly.
- **Commit messages:** explain *why*, not just what. Existing commits are the
  pattern.
- **Write for the ear.** Every agent-facing string is spoken by TTS. No
  markdown, no lists, no brackets, sentences under ~20 words. Read new prompt
  text aloud before committing it.
- **Health content:** never a diagnosis, never a dose, never a claim that a
  scheme amount is current. When adding scheme data, describe benefits
  qualitatively — amounts drift by state and budget cycle.

---

## Where to go next

Days 3–10 are unscheduled. Known gaps, roughly by value:

1. **Latency measurement.** How long escalation takes to reach the caller's ear
   is the number that matters most for an emergency, and it is unmeasured.
2. **Multi-turn guardrail pressure.** Every adversarial case is single-turn. A
   caller who asks for a dose four times, rephrasing each time, is untested.
3. **Regional languages.** A Marathi or Bengali caller currently gets an honest
   "I can't speak that" — safe, but a failure. Real coverage means a second
   voice and layer-1 phrases in that language.
4. **Devanagari red-flag phrases.** All Hindi phrases are romanised, matching
   what `nova-3` returns today. If STT ever emits Devanagari, layer 1 goes
   silent until phrases are added.
5. **Telephony.** SIP inbound would make this reachable by the people it is for.
   `BVCTelephony` noise cancellation is already wired for SIP participants.
6. **Conversation memory across a call** — currently every turn is stateless
   beyond the chat context.

Full gap list with reasoning is at the bottom of `RED_TEAM.md`.
