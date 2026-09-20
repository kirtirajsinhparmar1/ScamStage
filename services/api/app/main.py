from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import build_providers
from app.api.routes.diagnostics import router as diagnostics_router
from app.api.routes.health import router as health_router
from app.api.routes.sessions import router as sessions_router
from app.core.config import Settings
from app.database.memory import InMemorySessionRepository


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    classifier, voice = build_providers(settings)
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.state.settings = settings
    application.state.classifier = classifier
    application.state.voice = voice
    application.state.session_repo = InMemorySessionRepository()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.include_router(health_router, prefix="/api")
    application.include_router(sessions_router, prefix="/api")
    application.include_router(diagnostics_router, prefix="/api")
    return application


app = create_app()
