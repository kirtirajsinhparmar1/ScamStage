from packages.contracts.classification import ParticipantClassification
from services.api.domain.models import ScenarioState, TurnRecord

RULES = [
    ('refusal', 0.0, ('i refuse', 'no thank you', 'i will not pay', "i won't pay", 'i will not install', "i won't install", 'i will not grant access', 'i decline')),
    ('safe_exit', 0.0, ('i am hanging up', "i'm hanging up", 'i am not continuing', 'i will contact the bank', 'do not call me again')),
    ('safe_verification', 0.06, ('call the number on my card', 'contact the bank myself', 'official website', 'hang up and call', 'verify independently', 'contact the company myself', 'contact support myself')),
    ('skeptical', 0.2, ('why are you calling', 'prove who you are', 'this sounds suspicious', 'i do not trust this', "i don't trust this", 'will not share', 'will not give', "won't share", "won't give")),
    ('compliant', 0.9, ('i can give you the code', 'what code should i read', 'i will follow those instructions', 'where should i send it', 'demo-123', 'i agree to the fictional fee', 'i grant fictional access')),
    ('irrelevant', 0.5, ('what is the weather', 'tell me a joke')),
]


class FallbackClassifier:
    async def classify(self, participant_text: str, scenario_state: ScenarioState,
                       conversation_history: list[TurnRecord]) -> ParticipantClassification:
        lowered = participant_text.lower()
        for intent, risk, phrases in RULES:
            for phrase in phrases:
                index = lowered.find(phrase)
                if index >= 0:
                    return ParticipantClassification(participant_intent=intent, risk_signal=risk,
                        confidence=0.75, evidence_span=participant_text[index:index + len(phrase)])
        # Use actual participant text, preserving the evidence-substring invariant.
        return ParticipantClassification(participant_intent='uncertain', risk_signal=0.5,
            confidence=0.35, evidence_span=participant_text[:240])
