# SCAMSTAGE final judge demo runbook

SCAMSTAGE is a fictional fraud-awareness training simulator. It has no bank,
payment, account, or identity connection. Use synthetic practice responses only:
never enter a real password, account number, payment detail, verification code,
or personal information. The caller voice is synthetic and the visible notice
identifies the experience as fictional training.

## Start the demo

From the repository root:

```bash
.venv/bin/python -m services.api
```

Open <http://127.0.0.1:8000>. The same process serves the frontend, API, and
generated audio. For a hosting platform that supplies a port, use:

```bash
HOST=0.0.0.0 PORT=8000 .venv/bin/python -m services.api
```

The active judge configuration is `DIALOGUE_PROVIDER=ollama` with local
`qwen3:4b` caller wording and ElevenLabs audio when its credentials are
configured. If a caller response is unavailable, the call stays active and the
interface exposes **Retry caller response**; it does not substitute authored
active-call dialogue.

## Recommended five-turn voice flow

1. Leave **Fictional bank fraud** selected and choose **Start voice call**.
2. Point out the prominent fictional-training warning, invented organization,
   synthetic caller notice, no-real-information warning, risk visualization,
   provider labels, and timeline.
3. Let the live Ollama opening play. The interface should remain **Call in
   progress** and begin listening after playback. If browser speech recognition
   is unavailable, choose **Use text instead**; the same session continues.
4. Use these five synthetic responses, one at a time:

   1. `What exactly is this alert about?`
   2. `How do I know you are really from the credit union?`
   3. `I am uncomfortable continuing this conversation.`
   4. `I will call the number on my card instead.`
   5. `I am just going to hang up.`

   Each response should produce a live Ollama caller line, an ElevenLabs audio
   result when configured, a fast-safety-policy classification, updated risk,
   tactic/evidence labels, and another active turn. The call must still say
   **Call in progress** after turn five.
5. Click **End call safely**. Only this explicit action ends the call. Confirm
   that the immediate deterministic debrief shows the training risk indicator,
   boundaries, verification result, tactics, evidence, safer guidance, and the
   complete timeline. An optional Nemotron card may appear later without
   delaying the debrief.

Do not say or enter real credentials, codes, account details, payment details,
contact information, or personal information. The sample responses above are
fictional practice text.

## What to point out

- The fast safety policy is authoritative for participant classification, risk,
  tactics, rolling pressure strategy, evidence, and the end-only debrief.
- Ollama writes only one concise caller line within the selected deterministic
  strategy. It does not decide risk, tactics, state, scoring, or outcomes.
- Questions, skepticism, discomfort, apparent compliance, refusal, and “I am
  hanging up” do not auto-end the active call.
- The caller stays in character as a fictional caller. The visible training
  notice carries the disclaimer instead of repeating it in every line.
- ElevenLabs produces the synthetic voice when available. A missing audio file
  leaves readable transcript text and is labeled as a voice fallback.
- The explicit end action stops listening/audio, creates the deterministic
  debrief immediately, and then permits optional non-blocking Nemotron review.
- Browser autoplay may require pressing **Play** on the audio control. Speech
  recognition is browser-dependent; typed input remains available.

## Recovery

If Ollama fails, read the exact provider label, click **Retry caller response**,
and continue the same session. Do not refresh during the proof: refresh loses
the in-memory session. If ElevenLabs is unavailable, continue with the caller
transcript and record the truthful text-only voice status.
