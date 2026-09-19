from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import build_providers
from app.api.routes.health import router
from app.core.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    classifier, voice = build_providers(settings)
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.state.classifier = classifier
    application.state.voice = voice
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.include_router(router, prefix="/api")
    return application


app = create_app()
