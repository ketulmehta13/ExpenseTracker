from fastapi import APIRouter, Depends, Request

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
    }


@router.get("/v1/me")
async def me(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Echo the authenticated user: a quick end-to-end check of a token."""
    return {"id": user.id, "email": user.email}
