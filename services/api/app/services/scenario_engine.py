from app.domain.enums import Action, ScenarioState

_NEXT = {
    ScenarioState.INTRO: ScenarioState.AUTHORITY,
    ScenarioState.AUTHORITY: ScenarioState.URGENCY,
    ScenarioState.URGENCY: ScenarioState.VERIFICATION,
    ScenarioState.VERIFICATION: ScenarioState.COMPLETED,
}


class ScenarioEngine:
    """Pure transition skeleton. Session ownership and persistence come later."""

    def advance(self, state: ScenarioState, action: Action) -> ScenarioState:
        if state == ScenarioState.COMPLETED:
            raise ValueError("A completed scenario cannot advance")
        if action == Action.END_CALL:
            return ScenarioState.COMPLETED
        if action == Action.REQUEST_VERIFICATION:
            return ScenarioState.VERIFICATION
        if action == Action.CONTINUE:
            return _NEXT[state]
        raise ValueError(f"Unsupported action: {action}")
