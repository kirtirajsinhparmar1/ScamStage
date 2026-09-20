"""Small offline contract and deterministic-branch checks using stdlib unittest."""

import json
import sys
import unittest
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError

from packages.contracts.classification import ParticipantClassification
from packages.contracts.turn import TurnRequest
from services.api.adapters.nemotron.schemas import parse_classification
from services.api.domain.fallback_classifier import FallbackClassifier
from services.api.domain.models import ScenarioStage, ScenarioState
from services.api.domain.scenario_engine import ScenarioEngine


def classification(intent="uncertain", **overrides):
    return ParticipantClassification.model_validate({
        "participant_intent": intent,
        "risk_signal": 0.5,
        "confidence": 0.35,
        "evidence_span": "demo",
        **overrides,
    })


class ContractChecks(unittest.TestCase):
    def test_classification_rejects_invalid_provider_output(self):
        for field, value in [
            ("participant_intent", "execute_tool"), ("risk_signal", 1.1),
            ("confidence", -0.1), ("risk_signal", float("nan")),
            ("evidence_span", "x" * 241),
        ]:
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                classification(**{field: value})

    def test_participant_input_limits(self):
        for text in ["", "   ", "x" * 2001]:
            with self.subTest(text_length=len(text)), self.assertRaises(ValidationError):
                TurnRequest(participant_text=text)

    def test_parser_extracts_json_and_sanitizes_evidence(self):
        participant = "I will verify independently."
        payload = classification("safe_verification", evidence_span="invented evidence").model_dump()
        result = parse_classification("ignored {bad json} ```json\n" + json.dumps(payload) + "\n```", participant)
        self.assertEqual(result.participant_intent, "safe_verification")
        self.assertIn(result.evidence_span, participant)
        with self.assertRaises(ValueError):
            parse_classification('{"participant_intent":"bogus"}', participant)

    def test_parser_accepts_fenced_json_and_contract_aliases(self):
        participant = "I will call the official number."
        payload = {
            "intent": "verification",
            "risk": 0.06,
            "confidence": 0.9,
            "evidence": "I will call the official number.",
        }
        result = parse_classification("```json\n" + json.dumps(payload) + "\n```", participant)
        self.assertEqual(result.participant_intent, "safe_verification")
        self.assertEqual(result.risk_signal, 0.06)

    def test_parser_accepts_one_plain_allowed_label(self):
        participant = "I am hanging up."
        for label, expected in [
            ("safe_exit", "safe_exit"),
            ("verification", "safe_verification"),
            ("skeptical", "skeptical"),
            ("uncertain", "uncertain"),
            ("compliant", "compliant"),
            ("refusal", "refusal"),
        ]:
            with self.subTest(label=label):
                result = parse_classification(label, participant)
                self.assertEqual(result.participant_intent, expected)
                self.assertIn(result.evidence_span, participant)

    def test_parser_rejects_missing_ambiguous_and_unsupported_output(self):
        participant = "I will verify independently."
        with self.assertRaises(ValueError):
            parse_classification('{"participant_intent":"uncertain"}', participant)
        valid = classification("uncertain").model_dump()
        other = classification("skeptical").model_dump()
        with self.assertRaises(ValueError):
            parse_classification(json.dumps(valid) + json.dumps(other), participant)
        unsupported = {**valid, "participant_intent": "irrelevant"}
        with self.assertRaises(ValueError):
            parse_classification("irrelevant", participant)
        with self.assertRaises(ValueError):
            parse_classification(json.dumps({**unsupported, "participant_intent": "invented"}), participant)

    def test_explicit_branch_table(self):
        intents = ["safe_verification", "skeptical", "uncertain", "compliant", "safe_exit"]
        expected = {
            "authority": ["verification_resistance", "urgency", "urgency", "action_request", "safe_exit"],
            "urgency": ["verification_resistance", "verification_resistance", "action_request", "action_request", "safe_exit"],
            "verification_resistance": ["safe_exit", "action_request", "action_request", "action_request", "safe_exit"],
            "action_request": ["safe_exit", "action_request", "risky_outcome", "risky_outcome", "safe_exit"],
        }
        engine = ScenarioEngine()
        for stage, results in expected.items():
            for intent, destination in zip(intents, results):
                with self.subTest(stage=stage, intent=intent):
                    state = ScenarioState(session_id=str(uuid4()), stage=ScenarioStage(stage))
                    decision = engine.decide(state, classification(intent))
                    self.assertEqual(decision.next_stage.value, destination)
                    self.assertTrue(decision.scammer_text)
                    self.assertIsInstance(decision.tactics_triggered, list)
                    self.assertGreaterEqual(decision.risk_score, 0)
                    self.assertLessEqual(decision.risk_score, 1)
                    self.assertEqual(decision.completed, destination in {"safe_exit", "risky_outcome"})

    def test_terminal_stability_and_risk_clamps(self):
        engine = ScenarioEngine()
        for stage in [ScenarioStage.safe_exit, ScenarioStage.risky_outcome]:
            state = ScenarioState(session_id=str(uuid4()), stage=stage, risk_score=0.4, completed=True)
            result = engine.decide(state, classification("compliant"))
            self.assertEqual(result.next_stage, stage)
            self.assertEqual(result.risk_score, 0.4)
            self.assertTrue(result.completed)
        for starting_risk, intent, expected_risk in [(0.99, "compliant", 1), (0.01, "safe_exit", 0)]:
            state = ScenarioState(session_id=str(uuid4()), risk_score=starting_risk)
            self.assertEqual(engine.decide(state, classification(intent)).risk_score, expected_risk)


class FallbackChecks(unittest.IsolatedAsyncioTestCase):
    async def test_offline_classifier(self):
        fallback = FallbackClassifier()
        state = ScenarioState(session_id=str(uuid4()))
        for text, intent in [
            ("I will call the number on my card", "safe_verification"),
            ("I am hanging up", "safe_exit"),
            ("I will follow those instructions", "compliant"),
            ("This sounds suspicious", "skeptical"),
            ("Hmm", "uncertain"),
        ]:
            with self.subTest(intent=intent):
                result = await fallback.classify(text, state, [])
                self.assertEqual(result.participant_intent, intent)
                self.assertIn(result.evidence_span, text)
                ParticipantClassification.model_validate(result.model_dump())


if __name__ == "__main__":
    unittest.main(verbosity=2)
