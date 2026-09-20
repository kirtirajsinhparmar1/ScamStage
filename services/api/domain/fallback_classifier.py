import re

from packages.contracts.classification import ParticipantClassification
from services.api.domain.models import ScenarioState, TurnRecord

RULES = [
    ('refusal', 0.0, ('i refuse', 'no thank you', 'no thanks', 'i will not pay', "i won't pay", 'i will not install', "i won't install", 'i will not grant access', 'i decline', 'not sharing', 'not giving', 'do not share', 'do not give')),
    ('safe_exit', 0.0, ('i am hanging up', "i'm hanging up", 'i am not continuing', 'i will contact the bank', 'hang up and call', 'call the official number', 'do not call me again', 'end this call')),
    ('safe_verification', 0.06, ('call the number on my card', 'contact the bank myself', 'official website', 'verify independently', 'contact the company myself', 'contact support myself', 'find the official contact', 'look up the official')),
    ('skeptical', 0.2, ('why are you calling', 'prove who you are', 'this sounds suspicious', 'i do not trust this', "i don't trust this", 'why is this urgent', 'why are you rushing', 'is this really')),
    ('compliant', 0.9, ('i can give you the code', 'what code should i read', 'i will follow those instructions', 'where should i send it', 'demo-123', 'i agree to the fictional fee', 'i grant fictional access', 'i would give', 'i can provide', 'i will share', 'i will read', 'i can tell you', 'i will install', 'i will pay', 'i will provide')),
    ('irrelevant', 0.5, ('what is the weather', 'tell me a joke', 'what time is it', 'my favorite color')),
]

_REFUSAL_RE = re.compile(r"\b(?:no|not|never|won't|wouldn't|cannot|can't|do not|don't|i refuse|i decline)\b")
_COMPLIANCE_RE = re.compile(r"\b(?:give|provide|share|read|send|install|pay|grant|follow|confirm|tell)\b")
_QUESTION_RE = re.compile(r"\b(?:what|how|why|when|where|who|can|could|would)\b")
_CLARIFICATION_RE = re.compile(
    r"\b(?:what happened|what is this about|what do you need|what exactly are you looking for|"
    r"what are you looking for|what is your name|why did you call|why are you calling|"
    r"can you repeat|could you repeat|what do you mean|please explain|which login|which transfer|"
    r"how can i verify|how do i verify|how may i verify)\b"
)
_DELAY_RE = re.compile(
    r"\b(?:give me a minute|need more time|call back later|i am busy|i'm busy|"
    r"deal with it later|think about it|not right now)\b"
)
_VERIFICATION_TERMS = (
    'official number', 'number on the back', 'back of my card', 'official website',
    'official contact', 'trusted channel', 'verify independently', 'verify this',
    'call the bank', 'call the credit union', 'contact support', 'call support',
)


def _classification(intent: str, risk: float, confidence: float, participant_text: str, evidence: str) -> ParticipantClassification:
    return ParticipantClassification(
        participant_intent=intent,
        risk_signal=risk,
        confidence=confidence,
        evidence_span=evidence or participant_text[:240],
    )


class FallbackClassifier:
    def classify_fast(self, participant_text: str, scenario_state: ScenarioState,
                      conversation_history: list[TurnRecord]) -> ParticipantClassification:
        """Bounded local policy for the voice critical path.

        This deliberately maps natural language into the existing contract labels.
        Dialogue and state transitions remain authored by ScenarioEngine.
        """
        lowered = ' '.join(participant_text.lower().split())

        # Questions about a trusted callback or verification route are safer
        # verification intent, even when they contain a phrase that would be a
        # safe exit when stated as a decision (for example, "call the official
        # number").
        if _CLARIFICATION_RE.search(lowered):
            return _classification('uncertain', 0.5, 0.7, participant_text, participant_text[:240])
        if _QUESTION_RE.search(lowered) and any(term in lowered for term in _VERIFICATION_TERMS):
            return _classification('safe_verification', 0.06, 0.82, participant_text, participant_text[:240])
        if _DELAY_RE.search(lowered):
            return _classification('uncertain', 0.5, 0.7, participant_text, participant_text[:240])

        for intent, risk, phrases in RULES:
            for phrase in phrases:
                index = lowered.find(phrase)
                if index >= 0:
                    # Use the original text for evidence so the public contract
                    # always contains an exact participant-text substring.
                    original_index = participant_text.lower().find(phrase)
                    start = max(0, original_index)
                    return _classification(intent, risk, 0.84, participant_text,
                                           participant_text[start:start + len(phrase)])

        # Negation wins over a nearby compliance verb ("I will not share a code").
        if _REFUSAL_RE.search(lowered) and _COMPLIANCE_RE.search(lowered):
            match = re.search(_REFUSAL_RE.pattern, participant_text, re.IGNORECASE)
            return _classification('refusal', 0.0, 0.8, participant_text,
                                   match.group(0) if match else participant_text[:240])
        if any(token in lowered for token in ('hang up', 'end the call', 'call back myself', 'verify elsewhere')):
            return _classification('safe_exit', 0.0, 0.82, participant_text, participant_text[:240])
        if any(token in lowered for token in ('official', 'independently', 'trusted channel', 'verify')) and _QUESTION_RE.search(lowered):
            return _classification('safe_verification', 0.06, 0.79, participant_text, participant_text[:240])
        if any(token in lowered for token in ('suspicious', 'scam', 'really from', 'real caller', 'urgent', 'rush', 'pressure')):
            return _classification('skeptical', 0.2, 0.76, participant_text, participant_text[:240])
        if any(token in lowered for token in ('give', 'provide', 'share', 'read', 'send', 'install', 'pay', 'grant access', 'follow')):
            return _classification('compliant', 0.9, 0.72, participant_text, participant_text[:240])
        if any(token in lowered for token in ('weather', 'joke', 'favorite color', 'sports score')):
            return _classification('irrelevant', 0.5, 0.72, participant_text, participant_text[:240])
        return _classification('uncertain', 0.5, 0.42, participant_text, participant_text[:240])

    async def classify(self, participant_text: str, scenario_state: ScenarioState,
                       conversation_history: list[TurnRecord]) -> ParticipantClassification:
        result = self.classify_fast(participant_text, scenario_state, conversation_history)
        result.confidence = min(result.confidence, 0.75)
        return result
