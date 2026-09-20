# Milestone 2 implementation and verification

Verified September 19, 2026. **Milestone 2 is product-complete with graceful degradation, but the strict live Nemotron gate remains open after the final non-thinking request-shape check.** The deterministic suite and live ElevenLabs path pass; the final direct and application Nemotron checks timed out and correctly used the deterministic fallback. The acceptance test deliberately separates external-provider availability from scenario correctness.

## Narrow Nemotron reliability pass (latest results)

No scenario content, layout, credentials, model, or voice adapter changed. No dependencies were added.

### Final classifier request shape

- Model remains `nvidia/nemotron-3.5-lightning-30b-a3b`.
- The classifier request is non-streaming with `temperature=0` and `max_tokens=128`.
- The request sends `extra_body={"chat_template_kwargs": {"enable_thinking": false}}` and no `reasoning_budget`; the OpenAI-compatible wire body contains the flattened `chat_template_kwargs` object.
- The public `ParticipantClassification` contract is unchanged. The prompt now requires exactly one compact JSON object with no explanation, reasoning, markdown, code fences, or extra keys. The parser accepts valid/fenced JSON, existing contract field aliases, and one unambiguous allowed plain label; ambiguous or unsupported output still falls back. Retry policy, provider credentials, UI, scenario content, and ElevenLabs were not changed in this final check.

### Reliability behavior retained

- Explicit HTTP timeouts: connect 5s, read/inference 30s, write 10s, pool 5s. `NEMOTRON_TIMEOUT_SECONDS` remains the read-time setting; existing local value was already 30s. Additional settings allow phase-specific bounds. Each attempt also has an overall deadline equal to the sum of those phase limits (50s with defaults).
- One retry after 0.5s only for timeout, connection failure, HTTP 429, or HTTP 5xx. SDK retries remain disabled: at most two upstream attempts per classification. No retry for authentication, other permanent 4xx (including 408), or invalid classification output. After exhaustion, deterministic fallback occurs without another provider request.
- Classification remains non-streaming with the final fixed temperature/output bounds above. Deterministic fallback remains immediate after the existing bounded retry policy.
- Development failure logs include only provider, elapsed seconds, attempt, and an allowlisted failure category. Provider failures cross the domain boundary as sanitized errors, never raw exception text.
- Additive `classifier_fallback_reason` is saved in history and returned in turn responses. The UI renders `Classifier: nemotron` or a sanitized deterministic-fallback label such as `Classifier: deterministic fallback (timeout)` or `Classifier: deterministic fallback (invalid output)`.
- Branch/risk/debrief tests now inject explicit classification fixtures. Provider tests use an offline mock HTTP transport. Strict `--require-live` smoke makes one product classification request in the recruiter scenario (up to two bounded upstream attempts), requires both real providers and fetched audio, and does not assert a probabilistic branch choice. Combining `--all-scenarios` and `--require-live` is rejected before network access.
- Live browser checks use one selected session and verify the actual returned branch. Offline browser checks retain exact branch assertions. Playback waits up to five seconds for actual media-time advance instead of assuming 350ms is sufficient. Live harness deadlines cover the maximum configured adapter/voice budgets; they do not extend application timeouts.

### Exact verification results

| Check | Result |
| --- | --- |
| Direct synthetic diagnostic, original timeouts | `APITimeoutError`, 30.267s, category `timeout`; connect/read/write/pool each 30s |
| Final direct short live Nemotron classification | FAIL: no response returned; bounded attempt 1 timed out at 30.258s and attempt 2 at 30.064s, sanitized category `timeout`; `finish_reason`, `reasoning_content`, and content parse status were unavailable; model unchanged; connect/read/write/pool 5/30/10/5s |
| Python compilation, `services packages scripts` | PASS |
| Existing `check_contracts.py` plus parser cases | PASS, 9 tests (normal/fenced JSON, aliases, plain labels, missing/ambiguous/unsupported output) |
| Fixture-based `check_milestone2.py` | PASS, 15 tests |
| New `check_nemotron.py` | PASS, 8 tests with multiple transient/permanent status and timeout subcases |
| `npm --prefix apps/web run check` and browser script syntax | PASS |
| Credential-free HTTP smoke, `--all-scenarios` | PASS, bank compatibility plus all three safe/risky paths |
| Credential-free Chrome browser matrix | PASS, six outcomes, matching timeline/debrief, desktop/mobile, zero uncaught errors |
| Browser timeout-label fixture on recruiter scenario | PASS; only the reason was injected into an already-declared fallback response |
| Fresh `scripts/smoke_test.py --require-live` | FAIL (exit 1), genuine Nemotron assertion; observed `classifier_provider=fallback`, `classifier_fallback=true`, `classifier_fallback_reason=timeout`; turn elapsed 63.72s |
| Voice on that same fresh smoke turn | `voice_provider=elevenlabs`, `voice_fallback=false`, audio URL present |
| Manually driven non-default Chrome session on live server | Recruiter session completed `authority → safe_exit`; visible timeout fallback, matching timeline/debrief, disabled terminal input; opening and response audio played |

The final request-shape check used non-thinking mode and the 128-token bound, but the direct request and application turn timed out before a response object existed. Consequently, `finish_reason`, `reasoning_content` presence, and content parse status were unavailable for this run. The development-only diagnostic remains limited to allowlisted shape and parse metadata when a response exists; it does not log keys, headers, or raw response objects. The test correctly did **not** treat the returned fallback classification as a pass. Its authored recruiter opening audio was fetched successfully. The new transport tests separately prove retry-then-success, exhaustion, permanent-error no-retry, evidence sanitation, exact timeout/generation bounds, and sanitized development-only logging.

The first automated live browser attempt stopped before classification because a fixed 350ms audio observation saw ready state 4 but media time 0; the harness now polls for actual advancement. The existing recruiter browser session was then manually continued through Chrome debugging controls, without fabricating provider results. Opening playback advanced to 1.428s; terminal response playback advanced to 1.441s, ready state 4 and no media error. Its screenshot was inspected: selected recruiter scenario, `Classifier: deterministic fallback (timeout)`, ElevenLabs voice, safe-exit debrief, and 20% → 0% timeline risk all agreed. This proves graceful live-server degradation and real voice playback, **not** genuine live classification.

### Files changed in this reliability pass

- `services/api/config.py`, `services/api/adapters/nemotron/client.py`, `classifier.py`: phase timeouts, retry handling, final non-thinking request shape, and strict response-shape diagnostics.
- `services/api/adapters/nemotron/schemas.py`, `prompts.py`: bounded parser normalization and compact-output prompt contract.
- `services/api/ports/classifier.py`, `services/api/domain/orchestrator.py`: sanitized failure propagation.
- `packages/contracts/turn.py`, `response.py`, `apps/web/src/app.js`: additive reason and timeout label.
- `scripts/check_contracts.py`, `scripts/check_milestone2.py`, new `scripts/check_nemotron.py`, new `scripts/diagnose_nemotron.py`, `scripts/smoke_test.py`, `scripts/browser_check.mjs`: separated deterministic and external-availability checks plus parser coverage.
- `.env.example`, `README.md`, this report: timeout examples and verification commands. The ignored `.env` was not edited.

The unresolved limitation is NVIDIA hosted Nemotron inference from this environment: the final non-thinking request timed out before a response object was available. The preceding HTTP 200 diagnostic returned `finish_reason=length` with reasoning content and truncated content that the parser correctly rejected. Hosted inference is therefore best-effort; the visible deterministic fallback is the supported degradation path. Increasing retries indefinitely, changing the provider/model, or accepting fallback as live success would hide rather than satisfy the acceptance gate. The historical matrix below records earlier behavior and is not the current test strategy.

## Scenarios and API

- `fictional_bank_fraud_v1`: original bank scenario, still the default; original branch contract retained.
- `fictional_job_recruiter_v1`: fictional Fernwick Demo Careers recruiter scenario.
- `fictional_technical_support_v1`: fictional Cobalt Finch Demo Support scenario.

The validated catalog owns authored dialogue, stages, transition tables, tactics, risk deltas, debriefs, and safer-response guidance. Nemotron only classifies; it does not author caller dialogue. Existing provider credentials, model choices, and fallback behavior are preserved.

- Added `GET /api/scenarios`: safe scenario metadata for the picker.
- Extended `POST /api/sessions`: optional `scenario_id`; omitted body or `{}` retains the bank default. Unknown IDs return 422 before session allocation.
- Extended session/turn responses additively: scenario name, risk before, terminal debrief, and richer saved timeline evidence. Existing routes and response fields remain available. Completed sessions still reject turns with 409.

## Files changed

| Area | Files |
| --- | --- |
| Contracts | `packages/contracts/classification.py`, `session.py`, `turn.py`, `response.py` |
| Catalog | `services/api/scenarios/catalog.py` (new) |
| Domain | `services/api/domain/scenario_engine.py`, `orchestrator.py`, `fallback_classifier.py` |
| Classification context | `services/api/adapters/nemotron/classifier.py`, `prompts.py` |
| API | `services/api/main.py`, `services/api/routes/sessions.py`, `scenarios.py` (new) |
| Browser | `apps/web/index.html`, `apps/web/src/api.js`, `app.js`, `styles.css` |
| Verification | `scripts/check_milestone2.py` (new), `scripts/browser_check.mjs` (new), `scripts/smoke_test.py` |
| Documentation | `README.md`, this report |

Working adapters and persistence were reused. Scenario-specific behavior is now selected through catalog data instead of duplicating orchestrators or providers. No dependencies were added. The existing bank scenario definitions and contract test file were retained.

## Earlier Milestone 2 checks (historical)

| Check | Result |
| --- | --- |
| Python compilation: `python -m compileall -q services packages scripts` | PASS |
| Existing `scripts/check_contracts.py` | PASS: 6 tests |
| New `scripts/check_milestone2.py` | PASS: 14 tests |
| `npm run check` in `apps/web` | PASS: JavaScript syntax checks |
| `node --check scripts/browser_check.mjs` | PASS |
| HTTP smoke against fallback server, `--all-scenarios` | PASS: original bank flow plus all three safe/risky paths |
| Chrome integration against fallback server | PASS: all three selections, six safe/risky outcomes, matching debrief/timeline, restart, desktop/mobile layout, no uncaught browser errors |
| Live ElevenLabs | PASS: MP3 delivery and actual browser playback observed |
| Direct live Nemotron diagnostics | PASS: current prompt classified verification and compliance, including scenario context |
| Live browser bank safe-exit path | PASS: Nemotron classification and ElevenLabs playback |
| Full live smoke, `--all-scenarios --require-live` | FAIL: Nemotron timeout triggers fallback; repeated attempts did not pass |
| Full live browser matrix | FAIL: later bank risky-path turn fell back; all-three live matrix remains unverified |

The new tests cover definition validation, IDs, default compatibility, invalid-ID handling, refusal/safe/verification/resistance/escalation branches, risk continuity, evidence repair, fallback classification/provider failure, terminal stability, and timeline/debrief consistency.

## Earlier investigation and continuing deployment limitations

In the earlier pass, Nemotron calls through the running server repeatedly exceeded the configured 30-second timeout even though bounded direct adapter checks succeeded in roughly a second. Restarting with approved network access did not resolve it. Uvicorn and the direct diagnostic both use standard asyncio; no runtime cause was confirmed. The latest timeout/retry policy and fresh failures are recorded above. The simulator continues using its visible deterministic fallback.

The previous all-three live matrix has been replaced with deterministic scenario coverage and one strict live provider integration check; that live acceptance gate remains open. Live checks consume provider credits. No separate lint/typecheck tools are configured beyond the available npm syntax checks and Python compilation/tests. The installed Starlette test client emits an existing deprecation warning; dependencies were left unchanged.

Existing deployment limitations remain: localhost only, single process, in-memory sessions, local generated audio, no authentication or production retention policy. Practice inputs must be synthetic. The risk score is educational, not a fraud prediction.
