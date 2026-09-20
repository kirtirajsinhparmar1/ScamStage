# Provider references

The Nemotron adapter uses NVIDIA's hosted OpenAI-compatible chat completions API with `AsyncOpenAI`, non-streaming output, a short token budget, and no requested extended reasoning. The configured model is `nvidia/nemotron-3.5-lightning-30b-a3b`. Only final message content is parsed; the model never selects dialogue or invokes tools.

- [NVIDIA hosted LLM API reference](https://docs.api.nvidia.com/nim/re/reference/llm-apis)
- [NVIDIA model catalog and API credentials](https://build.nvidia.com/)

The ElevenLabs adapter posts deterministic text to `/v1/text-to-speech/{voice_id}`, authenticates through `xi-api-key`, and requests `mp3_44100_128` output with `eleven_multilingual_v2` by default. Audio is persisted locally and served by the application; no credentials reach the browser.

- [ElevenLabs create speech API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert)
- [ElevenLabs API quickstart](https://elevenlabs.io/docs/eleven-api/quickstart)

Both providers have bounded request timeouts. Nemotron retries once only for malformed classification output; provider transport failures immediately allow deterministic fallback. ElevenLabs failures immediately permit text-only continuation. Exceptions never include provider response bodies in application logs or returned errors.
