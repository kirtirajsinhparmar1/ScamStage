# Milestone 3: adaptive voice call mode

SCAMSTAGE now supports browser-based voice turn-taking that simulates a live
phone conversation. It is not telephony: there are no phone numbers, PSTN
connections, WebRTC streams, or real financial systems. Every organization,
account, response, and transaction in the exercise is fictional.

## Runtime flow

```text
Start voice call
  -> create a voice session
  -> play the authored fictional caller opening
  -> caller audio ends
  -> browser starts one SpeechRecognition turn
  -> final transcript is submitted to the existing HTTP turn endpoint
  -> fast local safety policy classifies the response
  -> deterministic scenario policy selects the tactic, risk, and outcome
  -> optional Gemini writes only bounded caller wording for active turns
  -> validator accepts Gemini wording or selects the authored fallback
  -> ElevenLabs returns caller audio, or text-only fallback is used
  -> audio ends and the browser listens again
```

Only the final recognized transcript is sent to the backend. SCAMSTAGE does
not store raw microphone audio. Browser speech recognition may use a browser
vendor's speech service; participants should use synthetic practice speech and
must never provide real personal information, passwords, account details,
payment details, or verification codes.

## Browser controller

`apps/web/src/voice.js` owns one call-session state machine. Its states are:

`idle`, `starting`, `requesting_microphone`, `caller_speaking`, `listening`,
`transcribing`, `submitting`, `processing`, `paused`, `terminal`, `error`, and
`text_fallback`.

The controller uses `window.SpeechRecognition` or
`window.webkitSpeechRecognition` with one non-continuous recognition turn at a
time, interim captions, and the browser language. Generation tokens and
submission guards prevent old audio or recognition callbacks from changing a
restarted session. A silence retry is bounded; the controller does not restart
the microphone forever.

If speech recognition is unavailable or permission is refused, the controller
keeps caller audio and the existing typed turn form available as a visible
fallback. If autoplay is blocked, the caller text remains visible and a
button lets the participant play or continue before listening begins.

## Fast adaptive policy

Voice turns use the local deterministic classifier immediately. It maps natural
language features into the existing contract labels, including skepticism,
safe verification, refusal, safe exit, compliance, irrelevant input, and
uncertain/clarification input. Voice turns do not wait for hosted Nemotron.

The scenario engine remains authoritative for intent, tactic, risk, stage, and
terminal outcome. Optional Gemini receives only sanitized fictional context and
can author the wording of an active non-terminal caller response. It cannot
change a policy decision or author terminal wording. Gemini output is bounded
and validated for length, prompt-injection text, real-world contact patterns,
unsafe information requests, and unsupported organizations; authored dialogue
is used on any rejection, timeout, missing key, or terminal turn. Authored
variants remain the deterministic fallback. The bank, recruiter, and
technical-support scenarios therefore react differently to
verification questions, skepticism, refusal, delay, clarification, and
fictional sensitive-information disclosure while remaining bounded to the
validated scenario catalog. A maximum of eight participant turns ends an
otherwise-open exercise with a training-limit debrief.

Voice sessions identify themselves with `interaction_mode: "voice"`; voice
turns use `input_mode: "voice"`. Existing text clients continue to omit both
optional fields and retain their prior behavior.

## Provider status

Provider fields describe the effective result, not merely an attempted call:

- `Classifier: fast safety policy` means the voice local policy classified the
  turn without a Nemotron request.
- `Classifier: Nemotron` means accepted hosted output determined a text-mode
  classification.
- `Classifier: deterministic fallback` means text-mode hosted classification
  failed or was rejected and the local fallback determined the result.
- `Voice: ElevenLabs` means caller audio was generated and returned.
- `Voice: text-only fallback` means caller text remains usable without audio.
- `Caller dialogue: Gemini` means validated Gemini wording was used for an
  active non-terminal turn.
- `Caller dialogue: authored fallback` means the scenario's safe authored
  wording was used because Gemini was disabled, unavailable, invalid, or the
  policy controlled a terminal response.
- `Independent evaluation: pending` means a terminal Nemotron evaluation was
  scheduled after the deterministic debrief was already returned.
- `Independent evaluation: NVIDIA Nemotron` means the bounded evaluator
  returned a validated second opinion; it never replaces the deterministic
  result.
- `Independent evaluation: deterministic fallback` means evaluation was
  unavailable and the deterministic debrief was retained.

Nemotron remains a best-effort provider. Its existing text-mode classifier is
not placed on the voice loop. After a terminal session, a separate bounded
evaluator receives a sanitized transcript in a background task. Timeout,
truncated/unsupported output, or missing credentials leaves the immediate
deterministic debrief authoritative and is labeled as fallback/unavailable.

## Demo

From the repository root:

```bash
.venv/bin/python -m services.api
```

Open <http://127.0.0.1:8000>, select **Fictional bank fraud**, and choose
**Start voice call**. Use only these synthetic responses:

1. Let the fictional caller opening play.
2. Say: `How do I know you are really from the bank?`
3. Notice the transcript is submitted automatically and the caller changes to
   verification/pressure language.
4. Say: `I am going to hang up and call the official number myself.`
5. Confirm the safe-exit debrief, tactics, evidence, risk, and timeline.

For the risky training branch, restart and use only:
`I would give the demo code DEMO-123.` The simulation uses that fictional value
to show the educational risky outcome; never use a real code or credential.

The same loop works for the fictional recruiter and technical-support
scenarios. The typed mode remains available for accessibility, unsupported
browsers, microphone permission refusal, and demo recovery.

## Known limitations

- Native speech recognition support varies by browser and may require a secure
  origin and microphone permission. Unsupported browsers use typed fallback.
- Browser autoplay policy may require pressing **Play caller response** before
  the next listening turn can begin.
- This is half-duplex browser turn-taking, not a full-duplex or real phone
  call; the microphone is closed while caller audio plays.
- Hosted Nemotron is best-effort and can time out or return invalid output. The
  deterministic fallback is the intentional reliability path.
- Sessions are in memory and generated audio is local runtime data. This is a
  synthetic localhost demo, not a production retention or account system.
