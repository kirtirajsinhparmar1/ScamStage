from contextlib import asynccontextmanager
import logging
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from services.api.adapters.elevenlabs.voice import ElevenLabsVoiceProvider
from services.api.adapters.nemotron.classifier import NemotronClassifier
from services.api.adapters.nemotron.evaluator import NemotronEvaluator
from services.api.adapters.ollama_dialogue import OllamaDialogueGenerator
from services.api.adapters.session_store import InMemorySessionStore
from services.api.config import ROOT, Settings
from services.api.domain.orchestrator import DialogueUnavailable, SessionCompleted, SessionNotFound, TurnOrchestrator
from services.api.routes import health, scenarios, sessions, turns
from services.api.scenarios.catalog import ScenarioNotFound

logger = logging.getLogger(__name__)


def _log_ollama_configuration(settings: Settings) -> None:
    """Log only non-sensitive local dialogue-provider diagnostics."""
    provider = settings.dialogue_provider.strip().lower()
    enabled = bool(settings.ollama_enabled)
    model_configured = bool(settings.ollama_model.strip())
    base_url_host = urlparse(settings.ollama_base_url).hostname or 'missing'
    ready = provider == 'ollama' and enabled and model_configured and bool(settings.ollama_base_url.strip())
    logger.info(
        'Ollama configuration: provider=%s enabled=%s model_configured=%s '
        'base_url_host=%s timeout_seconds=%s keep_alive=%s',
        provider, enabled, model_configured, base_url_host,
        settings.ollama_timeout_seconds, settings.ollama_keep_alive,
    )
    if not ready:
        logger.info(
            'Ollama dialogue diagnostics: model=%s request=skipped elapsed_ms=0 '
            'validation_passed=false reason=not_configured http_status=none',
            settings.ollama_model or 'missing',
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    _log_ollama_configuration(settings)
    settings.audio_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        classifier = NemotronClassifier(settings)
        voice = ElevenLabsVoiceProvider(settings)
        dialogue = (
            OllamaDialogueGenerator(settings)
            if settings.dialogue_provider.strip().lower() == 'ollama'
            else None
        )
        evaluator = NemotronEvaluator(settings) if settings.nemotron_api_key else None
        app.state.orchestrator = TurnOrchestrator(
            InMemorySessionStore(), classifier, voice, dialogue=dialogue, evaluator=evaluator,
        )
        try:
            yield
        finally:
            await classifier.close()
            await voice.close()
            if dialogue is not None:
                await dialogue.close()
            if evaluator is not None:
                await evaluator.close()

    app = FastAPI(title='SCAMSTAGE', lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(CORSMiddleware, allow_origins=settings.local_origins,
                       allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])

    @app.exception_handler(SessionNotFound)
    async def missing(request: Request, exc: SessionNotFound):
        return JSONResponse(status_code=404, content={'detail': 'Session not found. Start a new simulation.'})

    @app.exception_handler(ScenarioNotFound)
    async def missing_scenario(request: Request, exc: ScenarioNotFound):
        return JSONResponse(status_code=422, content={'detail': 'Unknown scenario. Choose an available scenario.'})

    @app.exception_handler(SessionCompleted)
    async def completed(request: Request, exc: SessionCompleted):
        return JSONResponse(status_code=409, content={'detail': 'Simulation completed. Start a new session.'})

    @app.exception_handler(DialogueUnavailable)
    async def dialogue_unavailable(request: Request, exc: DialogueUnavailable):
        messages = {
            'ollama_timeout': 'Local caller timed out. Confirm Ollama is running, then restart the simulation.',
            'ollama_invalid_output': 'Local caller returned an invalid response. Restart the simulation and try again.',
            'ollama_unavailable': 'Local caller is unavailable. Confirm Ollama is running, then restart the simulation.',
        }
        return JSONResponse(
            status_code=503,
            content={
                'detail': messages.get(exc.status, 'Local caller is unavailable. Restart the simulation.'),
                'dialogue_provider': exc.status,
            },
        )

    # Validation details need not echo arbitrary participant input back into errors.
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={'detail': 'Invalid request. Use a valid session ID and 1–2000 characters of fictional participant text.'})

    app.include_router(health.router)
    app.include_router(scenarios.router)
    app.include_router(sessions.router)
    app.include_router(turns.router)
    app.mount(settings.public_audio_path, StaticFiles(directory=settings.audio_dir), name='audio')
    app.mount('/src', StaticFiles(directory=ROOT / 'apps/web/src'), name='web-assets')

    @app.get('/', include_in_schema=False)
    async def index():
        return FileResponse(ROOT / 'apps/web/index.html')

    return app


app = create_app()
