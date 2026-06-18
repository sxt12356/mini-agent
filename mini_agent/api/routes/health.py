from typing import Any, Dict

from fastapi import APIRouter, Request
from pydantic import BaseModel

from mini_agent.core.session_store import RedisSessionStore


router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    redis_ok: bool
    active_sessions: int


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> Dict[str, Any]:
    store: RedisSessionStore = request.app.state.session_store
    redis_ok = await store.ping()

    return {
        "status": "ok" if redis_ok else "degraded",
        "redis_ok": redis_ok,
        "active_sessions": -1,
    }
