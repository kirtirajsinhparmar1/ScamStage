"""Diagnostic routes — verify provider connectivity.

These endpoints let you quickly test whether real API keys are configured
and reachable. They are safe to call with fake providers too.
"""

from fastapi import APIRouter, Request

from app.domain.enums import ScenarioState
from app.schemas.contracts import ClassificationResult, Contract

router = APIRouter(tags=["diagnostics"])


class DiagnosticResult(Contract):
    classifier_ok: bool
    classifier_result: ClassificationResult | None = None
    classifier_error: str | None = None
    voice_ok: bool
    voice_error: str | None = None


@router.get("/diagnostics/providers", response_model=DiagnosticResult)
async def check_providers(request: Request) -> DiagnosticResult:
    """Call classify and synthesize with test data and report success/failure."""
    classifier = request.app.state.classifier
    voice = request.app.state.voice

    # Test classifier
    classifier_ok = False
    classification = None
    classifier_error = None
    try:
        classification = await classifier.classify(
            "Can you verify your identity?", ScenarioState.AUTHORITY
        )
        classifier_ok = True
    except Exception as exc:
        classifier_error = f"{type(exc).__name__}: {exc}"

    # Test voice
    voice_ok = False
    voice_error = None
    try:
        await voice.synthesize("Hello, this is a test.")
        voice_ok = True  # None is a valid response (text-only mode)
    except Exception as exc:
        voice_error = f"{type(exc).__name__}: {exc}"

    return DiagnosticResult(
        classifier_ok=classifier_ok,
        classifier_result=classification,
        classifier_error=classifier_error,
        voice_ok=voice_ok,
        voice_error=voice_error,
    )
