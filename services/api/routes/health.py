from fastapi import APIRouter, Request

router = APIRouter()


@router.get('/health')
async def health(request: Request):
    settings = request.app.state.settings
    return {'status': 'ok', 'nemotron_configured': bool(settings.nemotron_api_key),
            'elevenlabs_configured': bool(settings.elevenlabs_api_key and settings.elevenlabs_voice_id)}
