"""Validate compact Nemotron output without exposing provider internals."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from pydantic import ValidationError

from packages.contracts.classification import ParticipantClassification


# These are input aliases only. The public response remains the existing
# ParticipantClassification contract.
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "participant_intent": (
        "participant_intent",
        "intent",
        "classification",
        "label",
        "category",
    ),
    "risk_signal": ("risk_signal", "risk", "risk_score"),
    "confidence": ("confidence", "certainty"),
    "evidence_span": ("evidence_span", "evidence"),
}

_INTENT_ALIASES = {"verification": "safe_verification"}
_PLAIN_LABEL_PATTERN = re.compile(
    r"(?<![a-z0-9_])(?:safe[\s_-]+verification|safe_exit|verification|skeptical|uncertain|compliant|refusal)(?![a-z0-9_])",
    re.IGNORECASE,
)
_PLAIN_LABELS: dict[str, tuple[str, float, float]] = {
    "safe_exit": ("safe_exit", 0.0, 0.75),
    "verification": ("safe_verification", 0.06, 0.75),
    "safe_verification": ("safe_verification", 0.06, 0.75),
    "skeptical": ("skeptical", 0.2, 0.75),
    "uncertain": ("uncertain", 0.5, 0.5),
    "compliant": ("compliant", 0.9, 0.75),
    "refusal": ("refusal", 0.0, 0.75),
}


def _mapping_value(value: object, key: str) -> object:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _normalize_payload(payload: object) -> dict[str, object] | None:
    if not isinstance(payload, Mapping):
        return None
    normalized: dict[str, object] = {}
    consumed: set[str] = set()
    for target, aliases in _FIELD_ALIASES.items():
        present = [alias for alias in aliases if alias in payload]
        if len(present) != 1:
            return None
        alias = present[0]
        consumed.add(alias)
        normalized[target] = payload[alias]
    # Multiple aliases or extra keys make the provider response ambiguous.
    if set(payload) != consumed:
        return None
    intent = normalized["participant_intent"]
    if isinstance(intent, str):
        normalized["participant_intent"] = _INTENT_ALIASES.get(intent.strip().lower(), intent.strip().lower())
    return normalized


def _validated_payload(payload: object, participant_text: str) -> ParticipantClassification | None:
    normalized = _normalize_payload(payload)
    if normalized is None:
        return None
    try:
        classification = ParticipantClassification.model_validate(normalized)
    except (TypeError, ValueError, ValidationError):
        return None
    if not classification.evidence_span or classification.evidence_span not in participant_text:
        classification.evidence_span = participant_text[:240]
    return classification


def _plain_classification(content: str, participant_text: str) -> ParticipantClassification | None:
    # A JSON-looking response with missing fields is not a plain label.
    if any(marker in content for marker in ("{", "}", "```")):
        return None
    matches = _PLAIN_LABEL_PATTERN.findall(content)
    if len(matches) != 1:
        return None
    label = matches[0].lower().replace(" ", "_").replace("-", "_")
    defaults = _PLAIN_LABELS.get(label)
    if defaults is None:
        return None
    intent, risk_signal, confidence = defaults
    return ParticipantClassification(
        participant_intent=intent,
        risk_signal=risk_signal,
        confidence=confidence,
        evidence_span=participant_text[:240],
    )


def parse_classification(content: str, participant_text: str) -> ParticipantClassification:
    """Parse one unambiguous JSON object or one exact plain label.

    Provider aliases are normalized into the existing public contract. Fenced
    JSON and a single object surrounded by harmless prose are accepted; two
    valid objects, unsupported labels, and partial objects are rejected.
    """
    if not isinstance(content, str):
        raise ValueError("Nemotron returned no valid classification")

    decoder = json.JSONDecoder()
    matches: list[ParticipantClassification] = []
    for index, char in enumerate(content):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(content[index:])
        except (TypeError, ValueError):
            continue
        classification = _validated_payload(payload, participant_text)
        if classification is not None:
            matches.append(classification)

    if len(matches) > 1:
        raise ValueError("Nemotron returned ambiguous classification objects")
    if matches:
        return matches[0]

    plain = _plain_classification(content, participant_text)
    if plain is not None:
        return plain
    raise ValueError("Nemotron returned no valid classification")


def redacted_content_preview(content: object, limit: int = 120) -> str:
    """Return a short development-log preview with common secrets removed."""
    if not isinstance(content, str):
        return "<non-text>"
    preview = re.sub(r"\s+", " ", content).strip()
    preview = re.sub(r"(?i)(api[_ -]?key|authorization|bearer)\s*[:=]\s*\S+", "<redacted-secret>", preview)
    preview = re.sub(r"https?://\S+", "<redacted-url>", preview)
    preview = re.sub(r"\b\d{4,}\b", "<redacted-number>", preview)
    if len(preview) > limit:
        preview = preview[:limit] + "…"
    return preview or "<empty>"


def response_content(message: object) -> str:
    """Extract text from the SDK message shape without logging raw objects."""
    content = _mapping_value(message, "content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = _mapping_value(item, "text")
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)
    return ""


def response_reasoning_content(message: object) -> str:
    """Read reasoning content only for internal parsing; never log its text."""
    reasoning = _mapping_value(message, "reasoning_content")
    return reasoning if isinstance(reasoning, str) else ""


def response_shape(result: object) -> dict[str, object]:
    """Collect allowlisted response metadata for development diagnostics."""
    choices = _mapping_value(result, "choices")
    if not isinstance(choices, list):
        choices = []
    choice = choices[0] if choices else None
    message = _mapping_value(choice, "message") if choice is not None else None
    content = _mapping_value(message, "content") if message is not None else None
    reasoning = _mapping_value(message, "reasoning_content") if message is not None else None
    finish_reason = _mapping_value(choice, "finish_reason") if choice is not None else None
    if not isinstance(finish_reason, str):
        finish_reason = "<missing>"
    return {
        "choices_count": len(choices),
        "finish_reason": finish_reason[:32],
        "content_exists": content is not None,
        "content_length": len(response_content(message)),
        "reasoning_content_exists": reasoning is not None,
        "content_preview": redacted_content_preview(content),
    }
