"""Nemotron tactic classifier — Person 3 implementation.

Uses NVIDIA's Nemotron API via httpx to classify scam tactics in participant
messages. Falls back gracefully if the API is unreachable.
"""

import json

import httpx
from app.domain.enums import ScenarioState
from app.schemas.contracts import ClassificationResult

# Default NVIDIA NIM endpoint for Nemotron chat completions.
_DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NemotronClassifier:
    """Real Nemotron-backed tactic classifier.

    Sends the participant message and current scenario context to the
    Nemotron chat-completion endpoint and parses the response into a
    ``ClassificationResult``.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        model: str = "mistralai/mistral-nemotron",
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._timeout = timeout

    async def classify(self, text: str, context: ScenarioState) -> ClassificationResult:
        """Classify scam tactics in *text* given the current scenario *context*."""
        system_prompt = (
            "You are a scam-tactic classifier. Given a participant's message "
            "and the current scenario phase, return ONLY valid JSON with keys: "
            '"participant_intent" (one of "unknown", "skeptical"), '
            '"detected_tactics" (list of strings), and '
            '"risk_level" (float 0-1). No extra text.'
        )
        user_prompt = f"Scenario phase: {context.value}\nParticipant message: {text}"

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 256,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        # Parse the model output — expect a JSON blob in the assistant message.
        raw = data["choices"][0]["message"]["content"]
        try:
            parsed = json.loads(raw)
            return ClassificationResult(
                participant_intent=parsed.get("participant_intent", "unknown"),
                detected_tactics=parsed.get("detected_tactics", []),
                risk_level=float(parsed.get("risk_level", 0)),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            # If the model output isn't valid JSON, return a safe default.
            return ClassificationResult()
