# SCAMSTAGE final judge demo runbook

SCAMSTAGE is a fictional fraud-awareness training simulator. It has no bank,
payment, account, or identity connection. Use synthetic practice responses only:
never enter a real password, account number, payment detail, verification code,
or personal information. The caller voice is synthetic.

## Start the demo

From the repository root:

```bash
.venv/bin/python -m services.api
```

Open <http://127.0.0.1:8000>. The same process serves the frontend, API, and
generated audio. For a hosting platform that supplies a port, use the same
entry point with `HOST` and `PORT`, for example:

```bash
HOST=0.0.0.0 PORT=8000 .venv/bin/python -m services.api
```

## Recommended 90-second voice flow

1. Leave **Fictional bank fraud** selected and choose **Start voice call**.
2. Point out the fictional-training warning, synthetic caller, and visible risk
   and evidence panels.
3. Let the opening audio finish. The call should automatically show **Your
   turn** and begin listening.
4. Say: `How do I know you are really from the bank?` The final transcript
   should appear and submit without pressing Send; the caller should change to
   verification pressure and listening should resume after its reply.
5. Say: `I am going to hang up and call the official number myself.` The call
   should end safely and show the debrief, tactics, evidence, risk change, and
   timeline.

For a second branch, restart the bank scenario and say only the synthetic
response `I would give the demo code DEMO-123.` to show the educational risky
outcome. Never use a real code or credential.

The recruiter and technical-support scenarios can be shown from the scenario
picker. Restarting or changing scenarios clears the prior transcript, audio,
evidence, timeline, provider status, and session state.

## What to point out

- The fast safety policy and selected scenario control intent, tactics, risk,
  and terminal outcomes. When Gemini is enabled, it writes only bounded
  active-turn caller wording; terminal wording remains authored.
- The provider story is explicit: fast safety policy controls the branch,
  Gemini is the optional caller-dialogue writer, ElevenLabs is the synthetic
  voice, and Nemotron is an independent post-conversation evaluator.
- Voice mode is browser-based turn-taking, not a real phone call. The browser
  microphone is closed while synthetic caller audio plays.
- The evidence and tactic labels explain why the branch became safer or riskier.
- The timeline makes the adaptive state change visible across turns.
- A provider label distinguishes preferred classification/audio from fallback.
- The terminal debrief appears immediately. The independent Nemotron card is
  first pending and may become complete; if unavailable it remains a truthful
  deterministic fallback.
- Browser autoplay may require pressing the audio player's **Play** control.
- If native browser speech recognition is unavailable or microphone permission
  is refused, choose **Use text instead**; caller audio and the typed turn form
  remain usable.

If ElevenLabs is unavailable, the response remains playable as readable caller
text and the interface labels the text-only fallback. If hosted Nemotron times
out or returns unsupported output, the deterministic classifier keeps the
scenario running and the UI labels the fallback; this is an intentional
reliability path, not live Nemotron success.

If Gemini is disabled or unavailable, the authored scenario dialogue continues
the conversation without blocking the safety policy. If Gemini is later
enabled, use only a real backend key in the ignored `.env`; never put it in
browser code or documentation. Do not describe authored fallback as Gemini
success.

## Final verification checklist

- [ ] Safety warning remains visible before and during the simulation.
- [ ] Bank, recruiter, and technical-support scenarios can each start.
- [ ] Safe-exit and risky-outcome branches are visible.
- [ ] Evidence, tactics, risk, confidence, provider status, and timeline update.
- [ ] Restart or scenario switching clears the previous session state.
- [ ] Audio plays when ElevenLabs is available, and text-only fallback works
      without it.
- [ ] No real credentials or personal data are entered during the demo.
