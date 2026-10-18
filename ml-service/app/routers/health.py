from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from app import __version__
from app.auth import CurrentUser, get_current_user

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict:
    categorizer = request.app.state.categorizer
    return {
        "status": "ok",
        "version": __version__,
        "models": {"categorizer": categorizer.version if categorizer else None},
        "llm": request.app.state.llm is not None,
    }


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    """Prometheus metrics. Aggregates only, but protected by METRICS_TOKEN when it is set."""
    token = request.app.state.settings.metrics_token
    if token and request.headers.get("authorization") != f"Bearer {token}":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or wrong metrics token")
    registry = request.app.state.metrics
    return Response(registry.render(), media_type=registry.content_type)


@router.get("/v1/me")
async def me(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Echo the authenticated user: a quick end-to-end check of a token."""
    return {"id": user.id, "email": user.email}
