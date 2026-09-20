# Milestone 1 architecture

SCAMSTAGE uses one FastAPI process to serve its static browser interface, JSON API, and generated MP3 files. Typed input is always supported. Optional browser speech recognition produces text through the same API contract.

```text
Browser text → route → TurnOrchestrator → TacticClassifier port
                                             ↓
                           Nemotron adapter / keyword fallback
                                             ↓
                              deterministic ScenarioEngine
                                             ↓
                              predefined dialogue template
                                             ↓
                              VoiceProvider → ElevenLabs
                                             ↓
                           local MP3 storage / text-only fallback
                                             ↓
                      SessionStore → API response → browser playback
```

Nemotron classifies the latest response using only the last four turns and current stage. Its final content is parsed as JSON, validated against the six-intent Pydantic contract, and given one retry for invalid output. Evidence is restricted to an actual substring of participant input. Hidden reasoning and raw provider internals are not returned. Participant content is untrusted data; it cannot provide new system instructions or execute tools.

The scenario engine exclusively controls transitions, risk updates, tactic labels, and dialogue. Safe verification initially meets verification resistance; continued safe verification ends the exercise. Compliance advances toward an action request and then an educational risky-outcome explanation. Terminal sessions cannot accept more turns.

ElevenLabs receives only short, predefined scenario text. Generated UUID session and turn identifiers determine audio paths; `opening` is the single allowed non-UUID clip name. The browser receives a local audio URL and never provider credentials. Failed synthesis does not discard the scenario turn.

Routes depend on the orchestrator, which uses classifier, voice, and session-store interfaces. An in-memory store is sufficient for this milestone and may later be replaced behind the same boundary. Run one process; restarting loses session state. Audio files persist locally and are intentionally ignored by git.

The response exposes classification evidence, before/after stages, risk, tactics, and provider fallback flags. These explain the decision without revealing model reasoning. The single institution, Lumenvale Demo Credit Union, is fictional. No banking or payment integration exists; only synthetic exercise responses belong in the application.

See [provider-reference.md](provider-reference.md) for official API references.
