# SCAMSTAGE

SCAMSTAGE is an adaptive synthetic-voice scam-awareness simulator for SteelHacks XIII. Participants type or optionally speak to a fictional fraud caller. NVIDIA Nemotron classifies their response; a deterministic scenario engine chooses the next tactic and predefined dialogue; ElevenLabs voices that dialogue. The interface shows the evidence, transition, tactics, and risk score behind each turn.

**This is a fictional training simulation. Lumenvale Demo Credit Union is invented. Never enter real personal information, account numbers, passwords, payment details, or one-time codes.** There are no connections to banks or payment systems. All practice responses must be synthetic; code-related dialogue explicitly warns against real codes.

## Run locally

Requires Python 3.11 or newer. Node and a frontend build step are not required. From the repository root:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** for the frontend. The same server serves the API, frontend, and audio. API documentation is at http://127.0.0.1:8000/docs. Start Simulation, send “I will call the number on my card instead,” then “I will follow those instructions.” The first response reaches verification resistance; the second reaches the action request. Continue with independent verification to end safely, or simulated compliance to see the educational risky outcome.

Browser autoplay policies may require pressing the audio player's Play control. Optional speech recognition depends on browser support and permission; typed input always works. Browser speech recognition may use the browser vendor's speech service, so use only synthetic practice speech.

## Milestone 2 scenarios

Choose a scenario before starting. Each uses an authored opening, dialogue, tactics,
branch table, risk changes, and outcome guidance:

| Scenario ID | Fictional organization |
| --- | --- |
| `fictional_bank_fraud_v1` (default) | Lumenvale Demo Credit Union |
| `fictional_job_recruiter_v1` | Fernwick Demo Careers |
| `fictional_technical_support_v1` | Cobalt Finch Demo Support |

“I am hanging up” ends safely; “Hmm” escalates pressure; “I will follow those
instructions” reaches an action request and then a risky outcome. Independent
verification first reaches verification resistance, then a safe exit. Explicit
refusal exits safely. The new scenarios route skepticism to verification; the
bank retains its original branch table for compatibility.

`GET /api/scenarios` returns public scenario metadata. `POST /api/sessions` accepts
an optional `scenario_id`; an empty or omitted body still starts the bank scenario.
Unknown IDs return 422 before any session or audio is created. Creation responses
add `scenario_name` and opening `tactics_triggered`. Turn responses add `risk_before`
and a terminal `debrief`; session details add the scenario name, debrief, and timeline
category, confidence, and risk-before/after values. Existing fields remain available.

The validated catalog lives in `services/api/scenarios/catalog.py`. The engine
looks up configuration by session scenario ID. Nemotron only classifies response
intent; it cannot author dialogue or change the catalog. The browser shows the
actual transition evidence and outcome, and offers “Try another scenario.”

## Provider configuration

Edit the ignored `.env` locally, or export equivalent environment variables. Never put keys in browser code or commit `.env`.

| Variable | Default / purpose |
| --- | --- |
| `NEMOTRON_BASE_URL` | `https://integrate.api.nvidia.com/v1` |
| `NEMOTRON_API_KEY` | NVIDIA API key; blank enables deterministic fallback |
| `NEMOTRON_MODEL` | `nvidia/nemotron-3.5-lightning-30b-a3b` |
| `NEMOTRON_TEMPERATURE` | `0` |
| `NEMOTRON_MAX_TOKENS` | `256` |
| `NEMOTRON_TIMEOUT_SECONDS` | `30`, inference/read timeout per attempt |
| `NEMOTRON_CONNECT_TIMEOUT_SECONDS` | `5` |
| `NEMOTRON_WRITE_TIMEOUT_SECONDS` | `10` |
| `NEMOTRON_POOL_TIMEOUT_SECONDS` | `5` |
| `ELEVENLABS_API_KEY` | ElevenLabs API key; blank enables text-only mode |
| `ELEVENLABS_VOICE_ID` | A voice available to your account |
| `ELEVENLABS_MODEL_ID` | `eleven_multilingual_v2` |
| `ELEVENLABS_TIMEOUT_SECONDS` | `15` |
| `APP_ENV` | `development` |
| `AUDIO_DIR` | `runtime/audio`, relative to the repository root |
| `PUBLIC_AUDIO_PATH` | `/audio` |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` |

Sign in at [NVIDIA Build](https://build.nvidia.com/), open the Nemotron model page, and create an API key for the hosted endpoint. The [official NVIDIA reference](https://docs.api.nvidia.com/nim/re/reference/llm-apis) lists this exact model and the chat-completions endpoint. Set `NEMOTRON_API_KEY`; the adapter uses the async OpenAI-compatible client and requests classification JSON only.

Create an API key in your ElevenLabs account and copy the ID of an available voice into `ELEVENLABS_VOICE_ID`. Ensure the key can use text-to-speech and the voice is accessible to that account. The adapter follows the [ElevenLabs speech API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert), requesting MP3 audio with the configured model. Restart the server after changing settings. A configured key does not guarantee access, quota, or provider availability.

## Verification

With the backend running, use another terminal:

```bash
.venv/bin/python -m compileall -q services packages scripts
.venv/bin/python scripts/check_contracts.py
.venv/bin/python scripts/check_milestone2.py
.venv/bin/python scripts/check_nemotron.py
.venv/bin/python scripts/smoke_test.py
npm --prefix apps/web run check
```

The smoke check creates a real session, sends safe-verification and compliant responses, validates classifications and distinct branches, retrieves saved history, and fetches every returned audio URL. It permits explicit fallbacks when providers are absent or unavailable. To require actual successful Nemotron classification and ElevenLabs audio:

```bash
.venv/bin/python scripts/smoke_test.py --require-live
```

The strict live check uses one recruiter classification and requires actual Nemotron
output and ElevenLabs audio. It does not assert the provider's exact branch choice.
Use `--all-scenarios` only against the credential-free server for the deterministic
branch matrix; combining it with `--require-live` is rejected.

To exercise the API without credentials even when `.env` contains keys, start a second server with empty environment overrides, then smoke-test it:

```bash
NEMOTRON_API_KEY= ELEVENLABS_API_KEY= ELEVENLABS_VOICE_ID= .venv/bin/python -m uvicorn services.api.main:app --host 127.0.0.1 --port 8001
```

```bash
.venv/bin/python scripts/smoke_test.py --base-url http://127.0.0.1:8001
.venv/bin/python scripts/smoke_test.py --base-url http://127.0.0.1:8001 --all-scenarios
```

The contract check does not call paid providers. The smoke check uses real adapters whenever credentials are configured and can consume provider credits. Audio fetching verifies delivery and content type; listen in the browser to confirm audible playback.

`scripts/browser_check.mjs` exercises the actual page in a local Chrome debugging
session on port 9222, using Node 22+ native WebSocket (no npm dependencies).
Run `node scripts/browser_check.mjs` against the fallback server, or add
`--base-url http://127.0.0.1:8000 --require-live --single-session --scenario-id fictional_job_recruiter_v1` to check live classification and
audio playback. It checks all picker options, safe/risky paths, debriefs, timelines,
disabled terminal input, mobile overflow, and browser errors; screenshots go to
`/private/tmp/scamstage-milestone2-{desktop,mobile}.png`.

## API examples

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/sessions -H 'Content-Type: application/json' -d '{}'
```

Copy the returned session ID into these requests:

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/SESSION_ID/turns -H 'Content-Type: application/json' -d '{"participant_text":"I will call the number on my card instead."}'
curl http://127.0.0.1:8000/api/sessions/SESSION_ID
```

Turn responses contain `analysis` (intent, risk signal, confidence, evidence), `stage_before`, `stage_after`, `risk_score`, `tactics_triggered`, deterministic `scammer_text`, optional `audio_url`, and provider/fallback indicators. Session retrieval includes saved history and timeline. `/health` reports whether credentials are configured, not whether providers are reachable.

## Architecture and files

```text
apps/web/                Static HTML, CSS, browser API/audio/speech handling
packages/contracts/      Shared Pydantic classification/session/turn/response schemas
services/api/main.py     FastAPI assembly and static mounts
services/api/routes/     Thin health, sessions, and turns routes
services/api/domain/     Orchestrator, scenario engine, fallback classifier
services/api/ports/      Classifier, voice, and persistence interfaces
services/api/adapters/   Nemotron, ElevenLabs, audio storage, session persistence
services/api/scenarios/  Validated three-scenario catalog and authored templates
scripts/                Contract validation and HTTP smoke harness
runtime/audio/          Generated MP3 files (ignored)
docs/                   Architecture and provider references
```

Flow: browser text → route → orchestrator → Nemotron classification → deterministic scenario engine → predefined response → ElevenLabs → saved turn and local audio URL → browser playback. Nemotron cannot generate dialogue or choose transitions. See [the architecture document](docs/milestone-1-architecture.md).

## Fallbacks and limitations

Missing, failed, or timed-out Nemotron calls use transparent keyword classification and return `classifier_provider: "fallback"`, `classifier_fallback: true`, and a sanitized `classifier_fallback_reason`. Timeout fallback is labeled explicitly in the UI. Timeout, connection, 429, and 5xx failures receive one retry after 0.5 seconds; permanent errors and invalid classification JSON do not retry. HTTP phase limits and an overall per-attempt cap bound waiting (with defaults, at most 100.5 seconds for classification including retry). Output is capped at 256 tokens and temperature at 0.2. Missing or failed ElevenLabs synthesis returns `audio_url: null`, `voice_fallback: true`, keeping the session usable. Development classifier logs contain only provider, elapsed time, attempt, and a sanitized reason.

This milestone has three scenarios, one process, in-memory sessions, and local audio storage. Sessions disappear on restart; generated audio remains until removed locally. Do not use multiple server workers. No authentication or production retention system is included: run on localhost for synthetic training only. Do not expose the server or audio directory publicly. Participant text is sent to NVIDIA when configured and remains in session memory; predetermined dialogue is sent to ElevenLabs. The simulator cannot guarantee detection of all sensitive information, so do not submit any real information. The risk score is an educational rule-based indicator, not a fraud prediction or financial advice. No production deployment, external bank connection, or additional runtime LLM is required.
