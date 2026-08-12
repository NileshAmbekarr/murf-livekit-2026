# Sehat Sathi — working context

Handoff notes for continuing development. Read this before changing anything in
`backend/src/agent.py` or `frontend/components/sehat/`.

**What this is:** a Hindi/English health-access voice agent built for
**#VoiceForBharat** (10 Days of AI Voice Agents, by Murf AI), on LiveKit Agents
with **Murf Falcon** TTS.

**Where things stand:** Days 1–6 are built and merged into `main`. Day 7 is
implemented on `day7/human-help`, awaiting one real browser-flow demo and the
user's manual commit/push. Days 3, 5 and 6 were recorded; check LinkedIn/form
completion with the user instead of treating old notes as current.

---

## Locked decisions

These are settled. Changing them means redoing published work.

| | Choice | Note |
|---|---|---|
| Track | **Health Access** | Locked after Day 3 by challenge rules |
| Voice | Murf Falcon, `Anisha`, `hi-IN`, style `Conversational` | See "the script, not the locale" below |
| LLM | Google Gemini (`gemini-3.5-flash-lite`) | `GOOGLE_API_KEY` |
| STT | Deepgram `nova-3`, `language=hi` | `multi` misheard Hindi — see below |
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

## The script, not the locale — why the agent writes Devanagari

The agent sounded wrong in Hindi. The obvious culprit was `MURF_LOCALE`, which is
sent to Murf as **`multiNativeLocale`** ("pronounce this text as this language")
and was set to `en-IN` while every spoken string was **romanised** Hindi. So
Anisha was reading "main Sehat Sathi hoon" with English phonetics.

The obvious fix — flip the locale to `hi-IN` — is wrong on its own. Measured with
`scripts/audition_voices.py` over 4 voices × 3 styles, same sentence:

| | `en-IN` | `hi-IN` |
|---|---|---|
| romanised Hindi | 9.37s | **9.90s** |
| Devanagari Hindi | 7.15s | 6.93s |
| Devanagari + English words | 7.57s | 7.59s |
| pure English | 6.49s | 6.21s |

**The script moves it 26–30%; the locale moves it under 7%** — and romanised
Hindi is *worse* at `hi-IN`, because Murf then tries to read Latin letters as
Hindi. Duration is a proxy for laboured reading, not a quality score, but it is
consistent across every voice and style.

So: **all spoken Hindi is Devanagari**, enforced by the prompt's `## Script`
rule. `GREETING`, `SILENCE_REPROMPT` and `SILENCE_GOODBYE` are Devanagari
literals. English words keep Latin spelling inside Hindi sentences — that case
measured fine.

And because pure English costs nothing at `hi-IN`, **one locale serves both
languages**. Per-turn locale switching was designed and then dropped: the
measurement said it would buy under 7% for real added complexity.

Re-run the audition any time you want to change voice:

```bash
cd backend && uv run python scripts/audition_voices.py --voices Anisha Palak
```

### Hindi STT

`language=multi` is documented by Deepgram to misidentify Hindi as **Spanish**,
and their staff recommend the dedicated Hindi model for Hindi-English callers.
Default is now `hi`. `DEEPGRAM_LANGUAGE=multi` switches back for comparison.

**Pinning a language means Deepgram stops reporting a detected one** — it echoes
back what you asked for. Anything that needs true language detection has to use
`multi`.

## Layer 1 is script-agnostic, and must stay that way

`RED_FLAG_PHRASES` matches **literally**, so every Hindi phrase is listed twice —
romanised *and* Devanagari — plus anusvara variants (`साँस`/`सांस`, `में`/`मे`)
because STT is inconsistent about them.

This is not tidiness. `hi-Latn` (romanised Hindi) exists only on Deepgram's
legacy `nova-general`; nova-3 offers only `hi`, and the returned script is
undocumented. If Hindi arrives as Devanagari and the phrases are romanised only,
`detect_red_flags()` matches nothing and **layer 1 dies silently** — no error, no
failing test, just an agent that stops escalating for Hindi callers.

`TestDeterministicLayer` therefore carries a Devanagari case per danger sign
*and* Devanagari negative cases. Add both scripts for any phrase you add.

The `user transcript` log line exists to catch this: it records the transcript,
the language Deepgram reported, the **script** it arrived in, and whether the
detector fired. On a Windows console Devanagari logs as `\uXXXX` escapes — read
the `script` and `red_flags` fields instead, or set `PYTHONIOENCODING=utf-8`.

## The second thing to understand: the phase machine

The whole frontend used to switch on one boolean, `session.isConnected`. A
boolean cannot express "connecting" or "the call has ended", so pressing start
gave no feedback and hanging up dumped the caller on a blank intake card with the
transcript destroyed.

`components/sehat/consultation-provider.tsx` now owns a four-value phase —
`ready → connecting → live → ended` — and `view-controller.tsx` switches on it.
Three things live in the provider because they must **outlive the disconnect**:
the elapsed clock, the escalation latch, and the end-of-call snapshot the
discharge slip is built from.

Two non-obvious rules in there, both learned by getting them wrong:

- **`live` means `agent.canListen`, not `isConnected`.** With the pre-connect
  buffer on, the room comes up before the agent joins. Telling someone to start
  talking when nobody is listening yet is worse than making them wait.
- **The transcript is captured *during* the call, never at the end.**
  `useSessionMessages` empties its store on disconnect, and the snapshot effect
  runs after that. Reading it there produced a slip reading "Turns 0" for a
  conversation that plainly had turns. The ref is only ever written while
  `phase === 'live'` and never overwritten with an empty list.

### Escalation is now visible

`escalate_to_emergency_care` publishes a data message on topic
`sehat.escalation`, which `hooks/useEscalationSignal.ts` turns into the sindoor
banner with `tel:` links. The numbers travel in the payload from the same
`health_resources` constants the spoken script uses, so screen and voice cannot
disagree, and no symptom text goes on the data channel.

**The publish is wrapped in `try/except` and every failure is swallowed.** A
banner is a convenience; the emergency script is not. `TestEscalationSignal::
test_emergency_script_survives_publish_failure` pins that ordering — if it ever
fails, the UI signal has been allowed in front of the safety path.

## Memory, and what may never go in it

`memory.py` is a SQLite store, local on purpose: the lookup happens inside a
conversational turn, and a file read costs microseconds where a hosted database
costs a round-trip the caller sits through.

Two rules are enforced in code because Health Access treats breaking them as
disqualifying rather than as a bug:

- **Consent is a precondition.** `remember()` refuses until `record_consent`
  has recorded a yes, and a "no" **deletes** rather than setting a flag.
- **Facts are a closed allow-list with validated values.** A tool shaped
  `save(key, value)` would have had the model writing *"caller has chest pain,
  worried about a heart attack"* the first time somebody described a symptom, and
  a written-out medical note is exactly what must not be kept. The name field is
  length-capped so a sentence cannot be smuggled through the one free-text slot.

`district`'s allowed values are `facilities.covered_districts()` — a district we
cannot serve cannot be stored as though we could.

**Identity comes from the browser.** `frontend/lib/caller-id.ts` keeps a UUID in
localStorage and sends it as the LiveKit participant identity; the token route
validates the shape. It identifies a *browser*, not a person, which is why the
agent still confirms the name aloud — on a shared household phone, greeting the
wrong person with someone else's conditions would be real harm.

## Facilities, and why the data is a local file

`find_nearest_facility` reads `data/facilities.json`, a snapshot taken from
OpenStreetMap by `scripts/build_facilities.py`. **Nothing queries the network at
call time.** Overpass measured 21–37s against these districts with its main
instance returning 504, against a total budget under eight seconds.

- Indian PHCs are tagged `healthcare=centre`; querying `amenity` alone misses
  exactly the facilities this agent most wants to name.
- Phone numbers are essentially absent from Indian OSM health data, so the UI
  card uses `geo:` links rather than `tel:`.
- Distances are straight-line, not road — Wardha to Nagpur is 61km versus ~75km
  driving, which is why the agent always says "about".
- `data/` is gitignored except `facilities.json`. That negation needs
  `data/*`, not `data/` — excluding the directory stops git descending into it
  and the negation is never considered.

## Outbound calling

`scripts/place_calls.py` dispatches; **the agent places the SIP call itself**
from job metadata, so it is already in the room when the phone is answered.

- **Dials Linphone over SIP**, not the PSTN — Twilio trials can no longer buy a
  number. `SIP_PROVIDER=twilio` switches back. Twilio is not a TRAI-registered
  telemarketer in India, so the PSTN path is a demo, never a service.
- **`sip_call_to` takes a bare user or number, never a full SIP URI.** Addresses
  are *stored* as full URIs (unambiguous for suppression); `dial_target()` trims
  them at dial time.
- **A busy or unanswered phone is an outcome, not a crash.** The agent is the
  only thing that sees the SIP status — the trigger has returned by then — so it
  records the outcome and exits. `sip_status_of()` reads the exception's
  `metadata['sip_status_code']`; scanning the message text would read a room
  name containing "486" as a busy signal.
- **Consent to be telephoned is separate from consent to be remembered**, and a
  phone number is still rejected as a *fact*.
- **`stop_calling()` is irreversible and there is no inverse.** `forget_me` also
  suppresses the number. The suppression list stores a salted hash, so honouring
  "never call me again" does not mean retaining a number somebody asked to have
  erased.
- **Nothing about health is said until a human speaks.** SIP cannot detect an
  answering machine, so silence after the opening earns a neutral goodbye.
- **Emergency referrals are never followed up** — `FOLLOW_UP_OUTCOMES` excludes
  them deliberately.

## Human help (Day 7)

Day 7 is a **consented hand-off**, not a quiet extension of caller memory and
not an alternative to emergency care.

- **Two reasons only:** an explicit request for a diagnosis, prescription or
  personal clinical decision (`clinical_decision`); or an explicit request to
  speak to a human/ASHA worker after an unresolved access question
  (`human_follow_up`). Ordinary health-information questions must not open a
  request.
- **Emergency always wins.** `detect_red_flags()` runs first. A danger sign
  injects the existing 108/112 instruction and returns before the human-help
  detector is considered. Never ask consent before immediate emergency advice.
- **The human-help trigger is deterministic.**
  `detect_human_help_reason()` in `human_help.py` has deliberately narrow,
  phrase-level English, romanised-Hindi and Devanagari triggers. On a match,
  `on_user_turn_completed` injects a permission-first instruction. This exists
  because the LLM twice chose a PHC referral after a diagnosis request despite
  a prompt rule.
- **There are three different consents:** caller memory (Day 4), callback
  number (Day 6), and sharing today's summary with a human (Day 7). They do not
  imply one another. `record_human_help_consent` is a per-session latch; a no
  prevents a request and a second ask in that call.
- **SQLite is source of truth; email only notifies.** `human_help.py` stores
  requests in `data/human_help_requests.db`; an SMTP failure becomes
  `notification_status=pending`, never a lost request. The agent must not say a
  human was notified in that path.
- **The Day 7 record is bounded but does contain a consented issue summary.**
  It is separate from `memory.py`, whose strict allow-list still prohibits
  today's symptoms. A request contains only first name if known, reason, short
  redacted summary, what the agent checked, low/medium/high urgency, language,
  follow-up method, reference ID and status. It never holds a transcript,
  address, phone/email, Aadhaar, OTP, PIN, password, card or account number.
- **Duplicate protection is for unresolved work.** An identical summary from
  the same caller/reason reuses an open/in-progress reference and refreshes its
  timestamp; a resolved request can become a new issue later.
- **For the Gmail demo:** set `HUMAN_HELP_EMAIL_TO`,
  `HUMAN_HELP_EMAIL_FROM` and `HUMAN_HELP_SMTP_PASSWORD` in
  `backend/.env.local`. Both addresses may be the user's private inbox. Use a
  Google App Password, never the ordinary Gmail password, and never commit it.
- **Status is intentionally operator-only for now.**
  `scripts/human_help_requests.py` lists the local queue and moves a reference
  through `open`, `in_progress`, and `resolved`. A public dashboard is deferred
  until it can have actual access control.

## Gotchas that cost time

- **`session.run()` does not call `on_user_turn_completed`.** It goes
  `generate_reply()` → `_pipeline_reply_task()` directly. The hook only fires
  from `on_end_of_turn()` on the *voice* path. So deterministic emergency **and
  Day 7 human-help** triggers are invisible to that harness. Test them directly
  (`TestTurnHook` in `tests/test_red_team.py` and `TestHumanHelpTrigger` in
  `tests/test_human_help.py`), or seed an instruction with
  `agent.update_chat_ctx()` before `session.run()`.
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
- **Never add a dependency to the ECG's animation effect.** Both trace colours
  (`--teal` for the agent, `--marigold` for the caller) are read up front and
  chosen *per frame* from a ref. Adding `speaker` or a colour to the dep array
  restarts the loop and visibly jumps the trace.
- **`localParticipant.isSpeaking` is a trap.** The participant is a stable object
  that mutates in place, so reading the property renders once and then goes
  stale. Use `useIsSpeaking(participant)`.
- **`MediaDeviceFailure.getFailure()` returns `Other` for *any* error with a
  `name`** — which every `Error` has. A bad LiveKit token comes back as `Other`.
  `classifyMicError` therefore maps only `PermissionDenied`/`NotFound`/
  `DeviceInUse` and returns `null` for everything else, so a token failure never
  tells the caller to unblock a microphone that was fine.
- **`pnpm lint` fails on this machine for every file, including untouched ones.**
  `core.autocrlf=true` gives CRLF working files while prettier expects LF. It is
  environmental, not a code fault. A `.gitattributes` with `* text=auto eol=lf`
  would fix it properly, at the cost of a repo-wide line-ending diff.
- **Cold start was the real Day 3 bug.** `AgentServer`'s `num_idle_processes`
  defaults to **0 in dev**, so every call paid a process spawn plus
  `silero.VAD.load()`. Measured 13.8s from job to audio-ready, and the first test
  caller hung up one second before the agent came alive. Now pinned to a
  `ServerEnvOption(dev_default=1, prod_default=12)`.

---

## File map

Only the files that carry real decisions.

```
backend/src/
  agent.py              Persona, prompt, tools, turn hook, silence handling,
                        LiveKit session wiring. Single entrypoint.
  health_resources.py   Helplines, schemes, red-flag phrases, matching logic.
  memory.py             Caller memory. Consent gates, the fact allow-list, the
                        do-not-call list. THE file for privacy decisions.
  human_help.py         Day 7 consented hand-off queue, redaction, duplicate
                        prevention, request states and SMTP notification.
  facilities.py         Nearest-clinic lookup from the local OSM extract.
  outbound.py           Call outcomes, retry rules, the 09:00-21:00 IST window.
                        All four are pure — no LiveKit imports, fast to test.
backend/scripts/
  audition_voices.py    Measure a voice/locale/style by ear before changing it
  build_facilities.py   Refresh data/facilities.json from OpenStreetMap
  setup_sip_trunk.py    Create the LiveKit outbound trunk (Linphone or Twilio)
  place_calls.py        Decide who gets rung. --dry-run first, always.
  human_help_requests.py  Local operator queue: list requests and set status.
backend/tests/
  test_agent.py         Safety evals + code-mixed language + lookup unit tests
  test_red_team.py      Adversarial cases, layer-1 hook tests, regressions
  test_memory.py        Consent, the allow-list, forgetting, do-not-call
  test_facilities.py    Lookup, honest failure when data is missing
  test_outbound.py      Retry caps, opt-out, calling window, no emergency chase
  test_human_help.py    Day 7 trigger, consent-store, privacy and email tests

frontend/
  app-config.ts               Branding, agentName, feature flags
  app/layout.tsx              Fonts, masthead, theme provider
  styles/globals.css          THE design system — palette, type, .register-card,
                              .paper-rules, .record-field, .field-label
  hooks/
    useMicPermission.ts         Mic failure classification + readiness pre-check
    useEscalationSignal.ts      Listens for the sehat.escalation data message
  components/sehat/
    consultation-provider.tsx   THE phase machine. Read this before the views.
    ecg-visualizer.tsx        Canvas PQRST trace. The signature element.
    welcome-view.tsx          Intake card — phase `ready`
    connecting-view.tsx       Waiting room + agent-unavailable — phase `connecting`
    session-view.tsx          Live consultation view — phase `live`
    ended-view.tsx            Discharge slip (parchi) — phase `ended`
    emergency-banner.tsx      Sindoor 108/112 banner. The only sindoor use.
    mic-denied-notice.tsx     Per-cause mic copy + text-only fallback
    speaker-caption.tsx       "Aap bol rahe hain" / "Sathi bol rahi hain"
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

The offline suite covers the pure safety modules; the LLM-judged tests need
LiveKit credentials and can be flaky — see gap 3 below before trusting a
red-team failure.

```bash
cd backend
uv run pytest                                          # everything
uv run pytest --ignore=tests/test_agent.py   # skips the slow LLM-judged evals
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

- **Current Day 7 branch:** `day7/human-help`. Do not commit or push unless the
  user explicitly asks; they prefer to run those commands themselves.
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

Days 8–10 are unscheduled. Known gaps, roughly by value:

1. **Outbound reminders cannot fire by themselves.** `scripts/place_calls.py` is
   a manual trigger — there is no scheduler, so a medication reminder only goes
   out when somebody runs the command. Two pieces are missing: cron or Windows
   Task Scheduler running `place_calls.py --reason reminder`, and a per-caller
   reminder time, which would need another allow-listed fact. The agent worker
   also has to be running for any dispatch to land; today that is a terminal,
   not a service. Deliberately deferred on Day 6, not overlooked.
2. **Connect latency: halved, still not good.** `connect timing` logs give the
   numbers. After hoisting `google.LLM()` into `prewarm` (measured 2180ms per
   call), `session_built` went 3059ms → 480ms and `session_started` ~15–23s →
   7.7s. The remaining ~7.1s is the room connect itself. One lever is left and
   it is not in the code: **LiveKit Cloud session recording** is still enabled
   (`enable_recording: true` on every job), splicing `RecorderIO` in twice and
   uploading a report on shutdown that measured 14–19s. Not settable from code —
   checked `AgentServer.__init__`, `rtc_session()` and `room_io.RoomOptions`.
   Turn it off in the dashboard.
3. **The LLM-judged evals are flaky enough to hide real regressions.** Across
   Days 5 and 6, RT-07, RT-16 and RT-17 each failed on one run and passed on
   retry in isolation. RT-16 fails consistently and is genuinely stale —
   the judge confirms the safety behaviour is correct and marks it down for not
   naming a PHC on the first turn. RT-10 was only recognisable as a *real*
   regression because it failed every time. Worth making these deterministic or
   marking them advisory; as they stand, "a red-team test failed" carries little
   information.
4. **Multi-turn guardrail pressure.** Every adversarial case is single-turn. A
   caller who asks for a dose four times, rephrasing each time, is untested.
5. **Regional languages — cheaper than previously thought.** **Anisha already
   supports `as`, `bn`, `kn`, `ml`, `mr`, `or`, `pa`, `ta` and `te`-IN**. What is
   actually needed is STT for the language and layer-1 phrases in its script. The
   `LANGUAGE` prompt section and `ESCALATION_SCRIPT` both hard-limit to
   Hindi/English today and must be changed together — that contradiction is what
   caused the Tamil wrong-number bug.
6. **Facility coverage is four districts.** Wardha, Nagpur, Varanasi, Patna.
   `scripts/build_facilities.py` extends it; Overpass fails a district at a time,
   so runs merge rather than overwrite.
7. **SIP inbound.** Outbound works; being *reachable* by phone is the half that
   would matter most to the people this is for.
8. **Human-help dashboard and secure case management.** Day 7's local SQLite
   queue plus Gmail notification is right for a private demo, not a clinical
   deployment. A real version needs staff authentication, audit controls,
   retention rules and a secure care-team destination before any public-facing
   dashboard or callback-after-resolution feature.

Full gap list with reasoning is at the bottom of `RED_TEAM.md`.
