# AGENTS.md

Monorepo for **Sehat Sathi**, a Hindi/English health-access voice agent powered
by Murf Falcon TTS and LiveKit Agents.

> **Read [`CLAUDE.md`](CLAUDE.md) first.** It carries the project's locked
> decisions, the layered safety design, bugs already found and fixed, and
> gotchas that cost real time. This file is the generic monorepo reference; that
> one is the working context. Where they disagree, `CLAUDE.md` wins.

## Repository structure

```
murf-livekit-2026/
├── backend/                    # Python voice agent
│   ├── src/agent.py            # Persona, prompt, tools, turn hook, pipeline
│   ├── src/health_resources.py # Helplines, schemes, red-flag matching
│   └── tests/                  # Safety evals + red-team suite
├── frontend/                   # Next.js UI
│   ├── app/                    # Pages and API routes
│   ├── components/sehat/       # Sehat Sathi UI (ECG visualizer, views)
│   ├── styles/globals.css      # The design system
│   └── app-config.ts           # Branding and feature config
├── CLAUDE.md                   # Working context — read this first
├── RED_TEAM.md                 # Adversarial results and findings
├── start_app.sh                # Start all services (macOS/Linux)
└── start_app.ps1               # Start all services (Windows)
```

## Backend

### Tech stack
- **Python 3.10+** with **uv** package manager
- **LiveKit Agents SDK** (`livekit-agents ~1.4`) — voice AI agent framework
- **Murf Falcon** (`livekit-murf`) — text-to-speech
- **Deepgram Nova-3** — speech-to-text
- **Google Gemini** — LLM
- **Silero VAD** + **LiveKit Turn Detector** — voice activity and turn detection

### Key file: `backend/src/agent.py`
This is the single entrypoint. It contains:
- `SYSTEM_PROMPT` — six labelled sections (IDENTITY, OBJECTIVES, KNOWLEDGE, LANGUAGE, GUARDRAILS, STYLE)
- `SehatSathi` class — extends `Agent`; tools are added via `@function_tool`
- `SehatSathi.on_user_turn_completed` — deterministic red-flag escalation, see `CLAUDE.md`
- `sehat_sathi()` — sets up the voice pipeline (STT → LLM → TTS) and connects to LiveKit
- `_install_silence_handling()` — re-prompt then graceful close on a silent caller
- `prewarm()` — pre-loads the Silero VAD model

Safety-critical data (helplines, schemes, red-flag phrases) lives in
`backend/src/health_resources.py` as pure functions with no LiveKit imports.

### Running the backend
```bash
cd backend
uv sync
uv run python src/agent.py download-files   # first time only
uv run python src/agent.py dev              # development
uv run python src/agent.py console          # terminal-only testing
```

### Environment variables
Copy `backend/.env.example` to `backend/.env.local`. Required keys:
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- `MURF_API_KEY`
- `DEEPGRAM_API_KEY`
- `GOOGLE_API_KEY`

### Code style
Uses **ruff** for linting and formatting:
```bash
uv run ruff check .
uv run ruff format .
```
Config is in `pyproject.toml` — 88 char line length, double quotes, space indent.

### Testing
Tests live in `backend/tests/`. 45 total: 29 run offline, the rest are LLM-judged
via LiveKit Cloud inference and need `LIVEKIT_URL`, `LIVEKIT_API_KEY` and
`LIVEKIT_API_SECRET`.

```bash
uv run pytest                                           # everything
uv run pytest -k "Deterministic or TurnHook or lookup"  # offline only, ~4s
```

When modifying the system prompt or adding tools, write tests first. Behavioural
tests call `session.run(user_input=...)` and use `.judge()`.

Note: `session.run()` does **not** invoke `on_user_turn_completed` — see the
gotchas in `CLAUDE.md` before testing anything that depends on that hook.

### Dependencies
Managed via `uv` and defined in `pyproject.toml`. Always use `uv sync` and `uv run` — never `pip install`.

## Frontend

### Tech stack
- **Next.js** (React, TypeScript)
- **pnpm** package manager
- **LiveKit Agents UI** (shadcn-based components)
- **Tailwind CSS**

### Key files
- `frontend/app-config.ts` — branding, feature flags, accent colors, visualizer config
- `frontend/app/page.tsx` — main page
- `frontend/app/api/token/route.ts` — LiveKit token endpoint
- `frontend/components/app/` — app-level logic (welcome view, view controller, theme)
- `frontend/components/agents-ui/` — voice UI components (visualizers, controls, chat)

### Running the frontend
```bash
cd frontend
pnpm install
pnpm dev
```

### Environment variables
Copy `frontend/.env.example` to `frontend/.env.local`. Required:
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- `AGENT_NAME` — must match `AGENT_NAME` in `backend/src/agent.py` (`sehat-sathi`)

### Linting
```bash
pnpm lint         # ESLint
pnpm format:check # Prettier
```

## Common tasks

### Change what the agent does
Edit `SYSTEM_PROMPT` in `backend/src/agent.py`. Read the GUARDRAILS notes in
`CLAUDE.md` first — two shipped bugs came from prompt edits that looked safe.

### Change the voice
Edit the `voice` argument in `murf.TTS(...)` in `backend/src/agent.py`. Browse voices at https://murf.ai/api/docs/voices-styles/voice-library.

### Add a tool to the agent
Add a method to the `SehatSathi` class in `backend/src/agent.py` with the
`@function_tool` decorator. Import `function_tool` and `RunContext` from
`livekit.agents`. Use the two existing tools as the pattern.

### Switch the LLM
Replace the `llm=google.LLM(...)` call in `agent.py`. For OpenAI: install `livekit-agents[openai]`, set `OPENAI_API_KEY`, import `openai` from `livekit.plugins`, and use `openai.LLM(...)`.

### Change frontend branding
Edit `frontend/app-config.ts` for company name, page title, logo paths, accent
colours and button text. Colours, type and the register styling live in
`frontend/styles/globals.css` — change tokens there rather than hardcoding in
components. See the design-system table in `CLAUDE.md`.

## Documentation references

- Murf Falcon TTS: https://murf.ai/api/docs/text-to-speech/streaming
- Murf Voice Library: https://murf.ai/api/docs/voices-styles/voice-library
- LiveKit Agents SDK: https://docs.livekit.io/agents
- LiveKit Agents UI: https://livekit.io/ui
- Deepgram STT: https://developers.deepgram.com
