from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from app.domain.enums import Action, ScenarioState
from app.schemas.contracts import ParticipantTurn, TurnResult

router = APIRouter()


@router.websocket("/sessions/{session_id}/stream")
async def session_stream(websocket: WebSocket, session_id: str) -> None:
    session_repo = websocket.app.state.session_repo
    classifier = websocket.app.state.classifier
    voice = websocket.app.state.voice
    scenario_engine = websocket.app.state.scenario_engine
    dialog_responder = websocket.app.state.dialog_responder

    session = session_repo.get_session(session_id)
    if not session:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Session not found",
        )
        return

    if session.status == "ended":
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Session already ended",
        )
        return

    await websocket.accept()

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            except Exception:
                await websocket.send_json({"error": "Invalid JSON format"})
                continue

            try:
                turn = ParticipantTurn.model_validate(data)
            except ValidationError as err:
                await websocket.send_json(
                    {
                        "error": "Invalid participant turn payload",
                        "details": err.errors(),
                    }
                )
                continue

            # 1. Run classifier on participant's input
            current_state = session.scenario_state
            classification = await classifier.classify(turn.text, current_state)

            # 2. Determine action
            text_lower = turn.text.lower()
            if any(
                phrase in text_lower
                for phrase in ("hang up", "end call", "goodbye", "bye", "disconnect")
            ):
                action = Action.END_CALL
            elif classification.participant_intent == "skeptical" or any(
                w in text_lower for w in ("verify", "verification", "badge")
            ):
                action = Action.REQUEST_VERIFICATION
            else:
                action = Action.CONTINUE

            # 3. Advance scenario state
            try:
                next_state = scenario_engine.advance(current_state, action)
            except ValueError:
                next_state = ScenarioState.COMPLETED

            is_complete = next_state == ScenarioState.COMPLETED
            new_status = "ended" if is_complete else "active"

            # 4. Update session store
            session = session_repo.update_session(
                session_id=session_id,
                scenario_state=next_state,
                status=new_status,
            )

            # 5. Generate scammer dialog response
            scammer_text = dialog_responder.respond(
                state=next_state,
                action=action,
                classification=classification,
            )

            # 6. Synthesize voice if available
            audio_url = await voice.synthesize(scammer_text)

            available_actions = (
                []
                if is_complete
                else [Action.CONTINUE, Action.REQUEST_VERIFICATION, Action.END_CALL]
            )

            turn_result = TurnResult(
                type="turn_result",
                session_id=session_id,
                speaker="scammer",
                text=scammer_text,
                audio_url=audio_url,
                scenario_state=next_state,
                detected_tactics=classification.detected_tactics,
                risk_level=classification.risk_level,
                available_actions=available_actions,
                is_complete=is_complete,
            )

            # 7. Record history
            session_repo.record_turn(
                session_id=session_id,
                turn_data={
                    "participant": turn.model_dump(),
                    "classification": classification.model_dump(),
                    "action": action.value,
                    "result": turn_result.model_dump(),
                },
            )

            # 8. Send result back to client
            await websocket.send_json(turn_result.model_dump(mode="json"))

            # 9. If completed, close stream cleanly
            if is_complete:
                await websocket.close(
                    code=status.WS_1000_NORMAL_CLOSURE,
                    reason="Scenario completed",
                )
                break

    except WebSocketDisconnect:
        pass
