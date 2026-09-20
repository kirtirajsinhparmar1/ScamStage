from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/scenarios')


@router.get('')
async def list_scenarios(request: Request):
    return request.app.state.orchestrator.catalog.list_scenarios()
