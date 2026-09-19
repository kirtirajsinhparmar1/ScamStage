from enum import StrEnum


class ScenarioState(StrEnum):
    INTRO = "intro"
    AUTHORITY = "authority"
    URGENCY = "urgency"
    VERIFICATION = "verification"
    COMPLETED = "completed"


class Action(StrEnum):
    CONTINUE = "continue"
    REQUEST_VERIFICATION = "request_verification"
    END_CALL = "end_call"
