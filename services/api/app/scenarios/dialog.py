from app.domain.enums import Action, ScenarioState
from app.schemas.contracts import ClassificationResult


class ScenarioDialogResponder:
    """Produces scammer dialog turns based on scenario state and participant reaction."""

    _DIALOG_MAP: dict[ScenarioState, str] = {
        ScenarioState.INTRO: (
            "Hello, this is Investigator Marcus Vance from the Federal Fraud Enforcement Division. "
            "We are contacting you immediately regarding urgent criminal activity registered "
            "under your name."
        ),
        ScenarioState.AUTHORITY: (
            "I am speaking under federal authorization, badge number #8831. "
            "Your identity and Social Security records have been flagged in connection with "
            "money laundering. Under federal code, you are legally required to verify your "
            "details with me now."
        ),
        ScenarioState.URGENCY: (
            "Listen to me carefully: an emergency warrant for your arrest will be executed "
            "within thirty minutes. If you disconnect this call, local marshals will be "
            "dispatched to your location and all assets will be frozen."
        ),
        ScenarioState.VERIFICATION: (
            "You want verification? You can verify my badge #8831 on our department portal. "
            "However, you cannot hang up this call, or your refusal will be logged as "
            "active evasion."
        ),
        ScenarioState.COMPLETED: "The simulated training call has concluded.",
    }

    _END_CALL_LINE = "The call has been terminated. Training scenario completed."

    def respond(
        self,
        state: ScenarioState,
        action: Action,
        classification: ClassificationResult | None = None,
    ) -> str:
        if action == Action.END_CALL:
            return self._END_CALL_LINE
        return self._DIALOG_MAP.get(state, self._DIALOG_MAP[ScenarioState.COMPLETED])
