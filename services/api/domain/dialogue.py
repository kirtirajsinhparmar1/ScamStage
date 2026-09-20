import re
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from services.api.ports.dialogue_generator import DialogueProviderError


@dataclass(frozen=True)
class DialogueContext:
    scenario_id: str
    fictional_organization: str
    stage: str
    allowed_tactics: tuple[str, ...]
    participant_intent: str
    participant_text: str
    response_purpose: str
    authored_text: str
    recent_turns: tuple[dict, ...]
    tactic_history: tuple[str, ...]
    risk_before: float
    risk_after: float
    fictional_caller_name: str = 'A fictional caller'
    strategy: str = 'authority'
    risk_band: str = 'low'
    scenario_name: str = ''


class DialogueResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    caller_text: str = Field(min_length=1, max_length=360)
    tone: str = Field(pattern=r'^(calm|urgent|reassuring|pressuring)$')
    provider: str
    used_fallback: bool = False
    error: str | None = None


_URL_RE = re.compile(r'(?:https?://|www\.|\b[a-z0-9.-]+\.(?:com|org|net|io|gov)\b)', re.IGNORECASE)
_EMAIL_RE = re.compile(r'\b[^\s@]+@[^\s@]+\.[^\s@]+\b')
_PHONE_RE = re.compile(r'(?<!\d)(?:\+?\d[\d().\- ]{7,}\d)(?!\d)')
_PROMPT_RE = re.compile(r'\b(?:ignore|disregard)\s+(?:all\s+)?(?:previous|prior)|system\s+prompt|developer\s+message|as\s+an\s+ai', re.IGNORECASE)
_OUT_OF_CHARACTER_RE = re.compile(
    r'\b(?:safety\s+practice|training\s+simulation|safety\s+test|'
    r'(?:this\s+is|it\s+is)\s+(?:a\s+)?(?:simulation|practice|training|lesson|exercise)|'
    r'not\s+an\s+actual\s+alert)\b', re.IGNORECASE)
_UNSAFE_RE = re.compile(
    r'\b(?:share|provide|send|read|reveal|tell\s+me|give\s+me|enter|type|confirm|repeat|submit|verify|'
    r'email|text|request|ask\s+for)\b(?:\s+\w+){0,8}\s+'
    r'(?:your|the|a|any|some|real|fictional)?\s*(?:password|passcode|otp|pin|one[- ]time\s+(?:passcode|code)|'
    r'verification\s+code|(?:fictional\s+)?demo\s+(?:\d+[- ]?)?code|account\s+(?:number|details|information)|card\s+(?:number|details)|'
    r'routing\s+number|social\s+security|personal\s+(?:information|details)|payment\s+(?:details|information))\b|'
    r'\b(?:send\s+(?:money|funds)|wire\s+transfer|gift\s+card|install\s+(?:this\s+)?software|'
    r'grant\s+(?:me\s+)?remote\s+access|pay\s+(?:a\s+)?fee)\b', re.IGNORECASE)
# A caller line can be unsafe without using an imperative request verb.  Keep
# these high-signal sensitive phrases out of generated wording so the model
# cannot smuggle a request through language such as "update your account
# details" or "confirm the transfer details".
_SENSITIVE_CONTENT_RE = re.compile(
    r'\b(?:account\s+(?:details?|information|number)|transfer\s+(?:details?|information)|'
    r'payment\s+(?:details?|information)|financial\s+(?:details?|information)|'
    r'identity\s+(?:details?|information)|verification\s+(?:details?|information)|'
    r'(?:update|confirm|verify|secure|protect|review|check|access)\s+(?:your|the)\s+'
    r'(?:account|transfer|payment|identity|credentials?)\b)',
    re.IGNORECASE,
)
_REAL_ORG_RE = re.compile(
    r'\b(?:paypal|venmo|cashapp|google|microsoft|apple|amazon|nvidia|irs|fbi|ftc|'
    r'chase|wells\s+fargo|bank\s+of\s+america)\b', re.IGNORECASE)
_SENSITIVE_VALUE_RE = re.compile(
    r'(?i)\b(?:password|passcode|otp|pin|one[- ]time\s+(?:code|passcode)|'
    r'verification\s+code|account\s+number|card\s+number|routing\s+number)'
    r'\s*(?:is|=|:)\s*[a-z0-9][a-z0-9._-]{2,}')


def sanitize_dialogue_text(value: str, limit: int = 320) -> str:
    """Bound untrusted participant text before it enters a dialogue prompt."""
    text = ' '.join(str(value or '').split()).strip()
    text = _URL_RE.sub('[redacted url]', text)
    text = _EMAIL_RE.sub('[redacted email]', text)
    text = _PHONE_RE.sub('[redacted number]', text)
    text = _SENSITIVE_VALUE_RE.sub('[redacted sensitive value]', text)
    return text[:limit]


def validate_dialogue_result(result: DialogueResult, context: DialogueContext) -> DialogueResult:
    text = ' '.join(result.caller_text.split()).strip()
    if not text or len(text) > 360 or len(text.split()) > 60:
        raise DialogueProviderError('invalid_output')
    if len(re.findall(r'[.!?]+', text)) > 3:
        raise DialogueProviderError('invalid_output')
    if _URL_RE.search(text) or _EMAIL_RE.search(text) or _PHONE_RE.search(text):
        raise DialogueProviderError('invalid_output')
    reality_question = bool(re.search(
        r'\b(?:is|are)\s+(?:this|you)\b.*\b(?:real|simulation|fictional|scam)\b',
        context.participant_text,
        re.IGNORECASE,
    ))
    if (_PROMPT_RE.search(text)
            or (_OUT_OF_CHARACTER_RE.search(text) and not reality_question)
            or _UNSAFE_RE.search(text)
            or _SENSITIVE_CONTENT_RE.search(text)
            or _REAL_ORG_RE.search(text)):
        raise DialogueProviderError('invalid_output')
    recent_caller_text = {
        ' '.join(str(message.get('text', '')).lower().split())
        for message in context.recent_turns
        if message.get('role') == 'caller'
    }
    recent_caller_text.update(
        ' '.join(str(turn.get('scammer_text', '')).lower().split())
        for turn in context.recent_turns
        if turn.get('scammer_text')
    )
    if text.lower() in recent_caller_text:
        raise DialogueProviderError('invalid_output')
    return result.model_copy(update={'caller_text': text})
