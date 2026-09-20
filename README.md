# SCAMSTAGE

SCAMSTAGE is an adaptive synthetic-voice scam-awareness simulator for SteelHacks XIII. Participants can use browser-based voice turn-taking that simulates a live phone conversation, or type to a fictional fraud caller. A fast local safety policy keeps turns immediate and remains authoritative for risk and state; local Ollama writes only bounded caller wording; ElevenLabs voices that wording; NVIDIA Nemotron independently evaluates the completed conversation when configured. The interface shows the evidence, transition, tactics, risk score, and provider truth behind each turn.

**This is a fictional training simulation. Lumenvale Demo Credit Union is invented. Never enter real personal information, account numbers, passwords, payment details, or one-time codes.** There are no connections to banks or payment systems. All practice responses must be synthetic; code-related dialogue explicitly warns against real codes.

## Run locally

Requires Python 3.11 or newer. Node and a frontend build step are not required. From the repository root:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m services.api
```

Open **http://127.0.0.1:8000** for the frontend. The same server serves the API, frontend, and audio. API documentation is at http://127.0.0.1:8000/docs. Start a voice call, let the live Ollama opening play, exchange as many fictional turns as you like, and click **End call safely** when ready. Only that explicit action creates the deterministic debrief.

The module entry point defaults to `127.0.0.1:8000` for local work. For a
platform-style process, provide the host and port through the environment:

```bash
HOST=0.0.0.0 PORT=8000 .venv/bin/python -m services.api
```

See the [final judge demo runbook](docs/person-3-demo-runbook.md) for a
short, reproducible presentation flow, and the [Milestone 3 voice architecture](docs/milestone-3-voice-adaptive-architecture.md)
for the call controller and fallback semantics.

Browser autoplay policies may require pressing the audio player's Play control. Optional speech recognition depends on browser support and permission; typed input always works. Browser speech recognition may use the browser vendor's speech service, so use only synthetic practice speech.

## Scenarios and open-ended calls

Choose a scenario before starting. Each uses a validated fictional organization,
rolling pressure strategies, tactic labels, risk changes, and outcome guidance:

| Scenario ID | Fictional organization |
| --- | --- |
| `fictional_bank_fraud_v1` (default) | Lumenvale Demo Credit Union |
| `fictional_job_recruiter_v1` | Fernwick Demo Careers |
| `fictional_technical_support_v1` | Cobalt Finch Demo Support |

Questions, skepticism, discomfort, refusal, apparent compliance, and “I am
hanging up” are recorded as active conversation turns. None of them ends the
call. The participant can continue the fictional conversation until clicking
**End call safely**; the rolling engine selects the next strategy while Ollama
writes only the caller wording.

`GET /api/scenarios` returns public scenario metadata. `POST /api/sessions` accepts
an optional `scenario_id`; an empty or omitted body still starts the bank scenario.
Unknown IDs return 422 before any session or audio is created. Creation responses
add `scenario_name`, `tactics_triggered`, `call_active`, and opening provider
status. Turn responses add `risk_before`, rolling `strategy`, and provider truth;
active turns remain non-terminal. `POST /api/sessions/{id}/end` is the normal
terminal action and immediately returns the deterministic debrief. Session
details preserve the scenario name, active/terminal state, debrief, and timeline
category, confidence, and risk-before/after values. Existing fields remain available.

The validated catalog lives in `services/api/scenarios/catalog.py`. The engine
looks up configuration by session scenario ID. The fast safety policy and rolling
engine decide intent, tactics, risk, strategy, and evidence. With
`DIALOGUE_PROVIDER=ollama`, every caller response—including the opening—is
generated live by local Ollama; invalid, unsafe, unavailable, or timed-out output
does not fall back to authored active-call dialogue. The session is preserved and
the browser exposes **Retry caller response**. Nemotron is an independent
post-call evaluator and cannot change the deterministic result. The browser shows
the actual transition evidence and outcome, and offers “Try another scenario.”

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
| `NEMOTRON_EVALUATION_TIMEOUT_SECONDS` | `5`, bounded terminal evaluation timeout |
| `GEMINI_API_KEY` | Legacy compatibility setting; unused by the active Ollama flow |
| `GEMINI_ENABLED` | `false`; Gemini is not the active caller provider |
| `GEMINI_MODEL` | Legacy compatibility setting |
| `GEMINI_TIMEOUT_SECONDS` | `2.5`, no-retry dialogue timeout |
| `GEMINI_BASE_URL` | `https://generativelanguage.googleapis.com` |
| `DIALOGUE_PROVIDER` | `ollama`; active caller wording provider |
| `OLLAMA_ENABLED` | `true`; disable to report local dialogue unavailable |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | `qwen3:4b` |
| `OLLAMA_TIMEOUT_SECONDS` | `8`, one request per caller turn |
| `OLLAMA_KEEP_ALIVE` | `30m`, keep the local model warm |
| `ELEVENLABS_API_KEY` | ElevenLabs API key; blank enables text-only mode |
| `ELEVENLABS_VOICE_ID` | A voice available to your account |
| `ELEVENLABS_MODEL_ID` | `eleven_multilingual_v2` |
| `ELEVENLABS_TIMEOUT_SECONDS` | `15` |
| `APP_ENV` | `development` |
| `HOST` | `127.0.0.1` for local development; set by the hosting platform when needed |
| `PORT` | `8000`, or the port supplied by the hosting platform |
| `AUDIO_DIR` | `runtime/audio`, relative to the repository root |
| `PUBLIC_AUDIO_PATH` | `/audio` |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` |

Sign in at [NVIDIA Build](https://build.nvidia.com/), open the Nemotron model page, and create an API key for the hosted endpoint. The [official NVIDIA reference](https://docs.api.nvidia.com/nim/re/reference/llm-apis) lists this exact model and the chat-completions endpoint. Set `NEMOTRON_API_KEY`; the adapter uses the async OpenAI-compatible client and requests classification JSON only.

Create an API key in your ElevenLabs account and copy the ID of an available voice into `ELEVENLABS_VOICE_ID`. Ensure the key can use text-to-speech and the voice is accessible to that account. The adapter follows the [ElevenLabs speech API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert), requesting MP3 audio with the configured model. Restart the server after changing settings. A configured key does not guarantee access, quota, or provider availability.

The active local flow uses `DIALOGUE_PROVIDER=ollama`, keeps `OLLAMA_ENABLED=true`,
and expects Ollama to serve `qwen3:4b`. Every caller response, including the
opening, is generated live by Ollama. If Ollama is unavailable, invalid, or
times out, the UI reports the exact sanitized status and exposes **Retry caller
response**; it never substitutes an authored active-call line. The deterministic
policy still owns risk, tactics, strategy, continuation, and terminal state.
The legacy Gemini settings remain documented for compatibility, but Gemini is
not called by the active Ollama application path.

Nemotron evaluation is scheduled only after a session becomes terminal. The
deterministic debrief is returned immediately; a bounded background evaluation
may later add an independent evaluation card. If Nemotron is unavailable or
returns invalid output, the UI truthfully retains the deterministic debrief.

## Verification

With the backend running, use another terminal:

```bash
.venv/bin/python -m compileall -q services packages scripts
.venv/bin/python scripts/check_contracts.py
.venv/bin/python scripts/check_milestone2.py
.venv/bin/python scripts/check_ollama_dialogue.py
.venv/bin/python scripts/check_nemotron.py
.venv/bin/python scripts/check_gemini_evaluation.py
.venv/bin/python scripts/smoke_test.py
node --check scripts/browser_check.mjs
npm --prefix apps/web run check
```

The smoke check creates real sessions, sends five active fictional responses,
verifies that the call remains active, explicitly ends it, validates the
deterministic debrief, retrieves saved history, and fetches every returned audio
URL. It permits explicit fallbacks when providers are absent or unavailable. To
require actual successful Ollama dialogue, ElevenLabs audio, and Nemotron
evaluation:

```bash
.venv/bin/python scripts/smoke_test.py --require-live
```

The strict live check uses the bank-fraud voice flow, requires five live Ollama
caller responses and ElevenLabs audio, and ends the call explicitly before
checking the terminal debrief. It does not assert the provider's exact strategy.
Use `--all-scenarios` only against the credential-free server; combining it with
`--require-live` is rejected.

To exercise the API without credentials even when `.env` contains keys, start a second server with empty environment overrides, then smoke-test it:

```bash
DIALOGUE_PROVIDER=authored_fallback OLLAMA_ENABLED=false NEMOTRON_API_KEY= ELEVENLABS_API_KEY= ELEVENLABS_VOICE_ID= HOST=127.0.0.1 PORT=8001 .venv/bin/python -m services.api
```

```bash
.venv/bin/python scripts/smoke_test.py --base-url http://127.0.0.1:8001
.venv/bin/python scripts/smoke_test.py --base-url http://127.0.0.1:8001 --all-scenarios
```

The contract check does not call paid providers. The smoke check uses real adapters whenever credentials are configured and can consume provider credits. Audio fetching verifies delivery and content type; listen in the browser to confirm audible playback.

`scripts/browser_check.mjs` exercises the actual page in a local Chrome debugging
session on port 9222, using Node 22+ native WebSocket (no npm dependencies).
Run `node scripts/browser_check.mjs` against the fallback server, or add
`--base-url http://127.0.0.1:8000 --require-live --single-session --scenario-id fictional_bank_fraud_v1` to check five live Ollama turns and
audio playback. It checks all picker options, rolling active turns, explicit
end-call debriefs, timelines, disabled terminal input, mobile overflow, and
browser errors; screenshots go to
`/private/tmp/scamstage-milestone2-{desktop,mobile}.png`.

## API examples

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/sessions -H 'Content-Type: application/json' -d '{}'
```

Copy the returned session ID into these requests:

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/SESSION_ID/turns -H 'Content-Type: application/json' -d '{"participant_text":"I will call the number on my card instead."}'
curl -X POST http://127.0.0.1:8000/api/sessions/SESSION_ID/end -H 'Content-Type: application/json' -d '{}'
curl http://127.0.0.1:8000/api/sessions/SESSION_ID
```

Turn responses contain `analysis` (intent, risk signal, confidence, evidence),
`stage_before`, `stage_after`, `strategy`, `risk_before`, `risk_score`,
`tactics_triggered`, live `scammer_text`, optional `audio_url`, and
provider/fallback indicators. Active turns are non-terminal. The `/end` action
returns the immediate deterministic debrief and schedules optional Nemotron
evaluation without blocking. Session retrieval includes saved history and
timeline. `/health` reports whether credentials are configured, not whether
providers are reachable.

## Architecture and files

```text
apps/web/                Static HTML, CSS, browser API/audio/speech handling
packages/contracts/      Shared Pydantic classification/session/turn/response schemas
services/api/main.py     FastAPI assembly and static mounts
services/api/routes/     Thin health, sessions, and turns routes
services/api/domain/     Orchestrator, scenario engine, fallback classifier
services/api/ports/      Classifier, voice, and persistence interfaces
services/api/adapters/   Ollama dialogue, Gemini compatibility, Nemotron/evaluation, ElevenLabs, audio storage, session persistence
services/api/scenarios/  Validated three-scenario catalog and authored templates
scripts/                Contract validation and HTTP smoke harness
runtime/audio/          Generated MP3 files (ignored)
docs/                   Architecture and provider references
```

Flow: browser text or final voice transcript → route → fast deterministic safety
policy → rolling scenario strategy → one bounded local Ollama wording request →
response validator → ElevenLabs or text fallback → saved turn and browser
playback. The call remains active until the participant invokes `/end`; that
action creates the deterministic debrief and starts a bounded background
Nemotron evaluator that cannot change it. See [the architecture document](docs/milestone-1-architecture.md)
and [the Milestone 3 voice/evaluation architecture](docs/milestone-3-voice-adaptive-architecture.md).

## Fallbacks and limitations

Voice and text active turns use the fast deterministic safety policy and do not
wait for Nemotron. Ollama is a short, strict local caller-dialogue writer only;
missing server, timeouts, invalid JSON, or unsafe content are labeled
`ollama_unavailable`, `ollama_timeout`, or `ollama_invalid_output`. The failed
caller response does not advance risk, strategy, history, or timeline; the UI
offers an explicit retry and never silently substitutes authored dialogue while
Ollama is active. It cannot change the deterministic policy. Missing or failed
ElevenLabs synthesis returns `audio_url: null`, `voice_fallback: true`, keeping
the session usable. Terminal Nemotron evaluation is bounded and asynchronous;
failures produce `evaluation_status: "fallback"` or `"unavailable"` while
preserving the immediate deterministic debrief. Development logs contain only
provider, elapsed time, attempt, and sanitized reasons.

This milestone has three scenarios, one process, in-memory sessions, and local audio storage. Sessions disappear on restart; generated audio remains until removed locally. Do not use multiple server workers. No authentication or production retention system is included: run on localhost for synthetic training only. Do not expose the server or audio directory publicly. Sanitized fictional context is sent only to the configured local Ollama process for caller wording; participant text may be sent to NVIDIA for text-mode classification, and a bounded sanitized terminal record may be sent to NVIDIA for independent evaluation; all remain in session memory. Ollama-validated dialogue is sent to ElevenLabs. The simulator cannot guarantee detection of all sensitive information, so do not submit any real information. The risk score is an educational rule-based indicator, not a fraud prediction or financial advice. No production deployment, external bank connection, or additional runtime LLM is required.
