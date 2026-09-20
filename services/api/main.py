from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from services.api.adapters.elevenlabs.voice import ElevenLabsVoiceProvider
from services.api.adapters.nemotron.classifier import NemotronClassifier
from services.api.adapters.session_store import InMemorySessionStore
from services.api.config import ROOT, Settings
from services.api.domain.orchestrator import SessionCompleted, SessionNotFound, TurnOrchestrator
from services.api.routes import health, scenarios, sessions, turns
from services.api.scenarios.catalog import ScenarioNotFound


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.audio_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        classifier = NemotronClassifier(settings)
        voice = ElevenLabsVoiceProvider(settings)
        app.state.orchestrator = TurnOrchestrator(InMemorySessionStore(), classifier, voice)
        try:
            yield
        finally:
            await classifier.close()
            await voice.close()

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
