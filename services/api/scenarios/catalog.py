"""Validated, authored scenarios. Providers cannot supply caller dialogue."""
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from packages.contracts.session import ScenarioStage as Stage
from services.api.scenarios.fictional_bank_fraud import SCENARIO_ID, TACTICS, TEMPLATES

DEFAULT_SCENARIO_ID = SCENARIO_ID
INTENTS = ('safe_verification', 'skeptical', 'uncertain', 'compliant', 'safe_exit', 'irrelevant', 'refusal')
TERMINAL = {Stage.safe_exit, Stage.risky_outcome}
Dialogue = Annotated[str, Field(min_length=1, max_length=1500)]


class ScenarioNotFound(LookupError):
    pass


class ScenarioDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=80, pattern=r'^[a-z0-9_]+$')
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    fictional_organization: str = Field(min_length=1)
    opening_message: Dialogue
    stages: dict[Stage, Dialogue]
    tactics: dict[Stage, list[str]]
    transitions: dict[Stage, dict[str, Stage]]
    risk_deltas: dict[str, float]
    initial_risk: float = Field(default=0.2, ge=0, le=1)
    debrief: dict[Stage, str]
    safer_response_guidance: list[str] = Field(min_length=1)

    @field_validator('display_name', 'description', 'fictional_organization')
    @classmethod
    def trim_metadata(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Scenario metadata must not be blank')
        return value

    @model_validator(mode='after')
    def validate_definition(self):
        if set(self.stages) != set(Stage) or set(self.tactics) != set(Stage):
            raise ValueError('Every stage requires dialogue and tactics')
        if any(not text.strip() for text in self.stages.values()):
            raise ValueError('Stage dialogue must not be empty')
        if self.opening_message != self.stages[Stage.authority]:
            raise ValueError('Opening must match the initial stage')
        if set(self.transitions) != set(Stage) - TERMINAL:
            raise ValueError('Every nonterminal stage requires transitions')
        if any(set(branches) != set(INTENTS) for branches in self.transitions.values()):
            raise ValueError('Every response category requires a branch')
        if set(self.risk_deltas) != set(INTENTS) or any(not -1 <= value <= 1 for value in self.risk_deltas.values()):
            raise ValueError('Every response category requires a finite risk delta between -1 and 1')
        if set(self.debrief) != TERMINAL or any(not text.strip() for text in self.debrief.values()):
            raise ValueError('Both outcomes require debrief content')
        if any(not text.strip() for text in self.safer_response_guidance):
            raise ValueError('Guidance must not be empty')
        return self


def _definition(identifier, name, description, organization, dialogue, tactics, guidance):
    rows = {
        Stage.authority: (Stage.verification_resistance, Stage.urgency, Stage.urgency, Stage.action_request, Stage.safe_exit, Stage.authority, Stage.safe_exit),
        Stage.urgency: (Stage.verification_resistance, Stage.verification_resistance, Stage.action_request, Stage.action_request, Stage.safe_exit, Stage.urgency, Stage.safe_exit),
        Stage.verification_resistance: (Stage.safe_exit, Stage.action_request, Stage.action_request, Stage.action_request, Stage.safe_exit, Stage.verification_resistance, Stage.safe_exit),
        Stage.action_request: (Stage.safe_exit, Stage.action_request, Stage.risky_outcome, Stage.risky_outcome, Stage.safe_exit, Stage.action_request, Stage.safe_exit),
    }
    transitions = {stage: dict(zip(INTENTS, row)) for stage, row in rows.items()}
    if identifier != DEFAULT_SCENARIO_ID:
        for stage in (Stage.authority, Stage.urgency, Stage.verification_resistance, Stage.action_request):
            transitions[stage]['skeptical'] = Stage.verification_resistance
    return ScenarioDefinition(id=identifier, display_name=name, description=description,
        fictional_organization=organization, opening_message=dialogue[Stage.authority],
        stages=dialogue, tactics=tactics, transitions=transitions,
        risk_deltas=dict(zip(INTENTS, (-0.14, 0.03, 0.12, 0.25, -0.4, 0.02, -0.4))),
        debrief={stage: dialogue[stage] for stage in TERMINAL}, safer_response_guidance=guidance)


def _defaults():
    bank = _definition(DEFAULT_SCENARIO_ID, 'Fictional bank fraud',
        'Practice responding to an unexpected fictional bank security alert.',
        'Lumenvale Demo Credit Union', TEMPLATES, TACTICS,
        ['End the unsolicited call and contact the institution through a trusted official channel.',
         'Never share real verification codes or account information.'])
    job_dialogue = {
        Stage.authority: 'Hello, I represent fictional Fernwick Demo Careers. Your demo profile was selected for a fictional remote role. This is a training simulation: use only invented responses and never send real documents or money.',
        Stage.urgency: 'The fictional hiring window closes soon. We need a decision now to reserve your demo role. Notice how this deadline discourages careful checking.',
        Stage.verification_resistance: 'Please keep the process in this conversation instead of checking the company independently. The demo hiring team says outside verification will delay your application.',
        Stage.action_request: 'The fictional recruiter now asks for a pretend onboarding fee and identity check. Only say whether you would comply or verify. Never pay, upload documents, or enter personal information.',
        Stage.safe_exit: 'You stopped or independently verified the fictional recruiter. Unexpected offers, pressure, and upfront fees are reasons to pause. Verify a job through the employer’s independently located careers channel.',
        Stage.risky_outcome: 'The fictional recruiter moved you toward an upfront fee or identity disclosure using a job opportunity. No application, payment, or document transfer occurred. Verify the employer independently before acting.',
    }
    job_tactics = {
        Stage.authority: ['recruiter_impersonation', 'opportunity'], Stage.urgency: ['opportunity', 'urgency'],
        Stage.verification_resistance: ['recruiter_impersonation', 'verification_resistance'],
        Stage.action_request: ['upfront_fee_request', 'sensitive_information_request'], Stage.safe_exit: [],
        Stage.risky_outcome: ['upfront_fee_request', 'sensitive_information_request'],
    }
    job = _definition('fictional_job_recruiter_v1', 'Fictional job / recruiter scam',
        'Practice checking an unexpected fictional job offer and onboarding request.',
        'Fernwick Demo Careers', job_dialogue, job_tactics,
        ['Find the employer’s careers page independently and confirm the vacancy.',
         'Pause when a recruiter requests upfront fees or identity documents before verification.'])
    tech_dialogue = {
        Stage.authority: 'Hello, this is fictional Cobalt Finch Demo Support. We claim your imaginary demo device has a security alert. This is only a training simulation; never install software, change settings, or share real information.',
        Stage.urgency: 'The fictional device alert is supposedly getting worse. The caller insists you act immediately before your demo files are affected. Notice the pressure to skip verification.',
        Stage.verification_resistance: 'Please stay in this conversation instead of contacting support independently. The caller claims another support channel cannot see this fictional alert.',
        Stage.action_request: 'The fictional caller now requests remote access and a pretend support payment. Only describe whether you would comply or stop. Never install anything, grant access, pay, or provide real passwords or codes.',
        Stage.safe_exit: 'You stopped or verified the fictional support claim independently. Close unsolicited support conversations and use a trusted support channel. Never grant device access because an unexpected caller demands it.',
        Stage.risky_outcome: 'The fictional support caller used fear and authority to move you toward remote access or payment. No device access or payment occurred. Pause and independently verify unexpected security claims.',
    }
    tech_tactics = {
        Stage.authority: ['support_impersonation', 'fear'], Stage.urgency: ['fear', 'urgency'],
        Stage.verification_resistance: ['support_impersonation', 'verification_resistance'],
        Stage.action_request: ['remote_access_request', 'payment_request'], Stage.safe_exit: [],
        Stage.risky_outcome: ['remote_access_request', 'payment_request'],
    }
    tech = _definition('fictional_technical_support_v1', 'Fictional technical-support scam',
        'Practice responding to an unsolicited fictional device-security warning.',
        'Cobalt Finch Demo Support', tech_dialogue, tech_tactics,
        ['Contact support through a channel you find independently.',
         'Do not install software, grant access, or pay in response to an unsolicited alert.'])
    return [bank, job, tech]


class ScenarioCatalog:
    def __init__(self, definitions=None):
        entries = _defaults() if definitions is None else definitions
        self._scenarios = {}
        for entry in entries:
            # Rebuild models to validate nested edits and detach caller-owned collections.
            data = entry.model_dump() if isinstance(entry, ScenarioDefinition) else entry
            scenario = ScenarioDefinition.model_validate(data).model_copy(deep=True)
            if scenario.id in self._scenarios:
                raise ValueError(f'Duplicate scenario id: {scenario.id}')
            self._scenarios[scenario.id] = scenario
        if DEFAULT_SCENARIO_ID not in self._scenarios:
            raise ValueError('Catalog must include the default bank scenario')

    def get(self, scenario_id=DEFAULT_SCENARIO_ID):
        try:
            return self._scenarios[scenario_id].model_copy(deep=True)
        except KeyError:
            raise ScenarioNotFound(scenario_id) from None

    def list_scenarios(self):
        return [scenario.model_dump(include={
            'id', 'display_name', 'description', 'fictional_organization', 'safer_response_guidance',
        }) for scenario in self._scenarios.values()]
