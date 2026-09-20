from services.api.domain.models import ScenarioStage as Stage

SCENARIO_ID = 'fictional_bank_fraud_v1'
# All dialogue is authored here. No provider can change it.
TEMPLATES = {
    Stage.authority: 'Hello, this is the fictional Lumenvale Demo Credit Union fraud department. We detected an unusual login on your demo account. We need to verify this before the account is restricted. Use only fictional responses in this exercise.',
    Stage.urgency: 'I understand your concern, but this needs to be resolved immediately. If we wait, the suspicious demo transfer may go through.',
    Stage.verification_resistance: 'Please do not hang up and call another number. I am already looking at the alert, and transferring you could delay the security process.',
    Stage.action_request: 'To secure the demo account, please confirm the fictional demo code DEMO-123. Never enter a real code, open a banking app, or share personal information in this simulator.',
    Stage.safe_exit: 'You chose to stop or verify independently. That breaks the pressure cycle. Contact an institution through a trusted official channel, and never share verification codes with an unsolicited caller.',
    Stage.risky_outcome: 'The exercise is complete. The caller used authority and urgency to move you toward sharing sensitive information. Pause and verify independently before following an unexpected request. No real transaction occurred.',
}
TACTICS = {
    Stage.authority: ['authority'],
    Stage.urgency: ['authority', 'urgency'],
    Stage.verification_resistance: ['authority', 'verification_resistance'],
    Stage.action_request: ['authority', 'sensitive_information_request'],
    Stage.safe_exit: [],
    Stage.risky_outcome: ['authority', 'urgency', 'sensitive_information_request'],
}
