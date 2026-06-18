import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from mini_agent.api.deps import get_rate_limited_current_user
from mini_agent.api.routes.sessions import (
    PendingApprovalView,
    load_or_create_agent_session,
    serialize_pending_approval,
)
from mini_agent.core.auth import CurrentUser
from mini_agent.core.observability import AgentTracer, safe_preview
from mini_agent.core.rate_limit import RateLimitResult, rate_limit_headers
from mini_agent.core.session_store import RedisSessionStore, SessionBusyError


router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="用户输入。")
    session_id: Optional[str] = Field(
        None,
        description="已有会话 ID。第一次请求可以不传。",
    )


class RateLimitView(BaseModel):
    scope: str
    limit: int
    count: int
    remaining: int
    retry_after_seconds: int


class ChatResponse(BaseModel):
    session_id: str
    trace_id: str
    request_id: str
    answer: str
    last_order_id: Optional[str]
    pending_approval: Optional[PendingApprovalView]
    rate_limit: Optional[RateLimitView]
    created_at: float


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(get_rate_limited_current_user),
) -> Dict[str, Any]:
    store: RedisSessionStore = request.app.state.session_store

    chat_rate: Optional[RateLimitResult] = getattr(
        request.state,
        "chat_rate_limit",
        None,
    )

    if chat_rate:
        for key, value in rate_limit_headers(chat_rate).items():
            response.headers[key] = value

    session_id = req.session_id or str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    tracer = AgentTracer(
        request_id=request_id,
        session_id=session_id,
        user_id=current_user.user_id,
    )

    try:
        async with store.session_lock(session_id):
            loaded_session_id, session, payload = await load_or_create_agent_session(
                store=store,
                session_id=req.session_id,
                current_user=current_user,
            )

            session_id = loaded_session_id
            tracer.session_id = session_id

            with tracer.span(
                "http.post./chat",
                kind="server",
                attributes={
                    "session_id": session_id,
                    "user_id": current_user.user_id,
                    "username": current_user.username,
                    "message_preview": safe_preview(req.message),
                    "has_existing_session": req.session_id is not None,
                    "rate_limit_remaining": chat_rate.remaining if chat_rate else None,
                },
            ):
                answer = await run_in_threadpool(
                    session.send,
                    req.message,
                    tracer,
                )

            await store.save(
                session_id=session_id,
                user_id=current_user.user_id,
                agent_state=session.to_state(),
                created_at=payload["created_at"] if payload else None,
            )

    except SessionBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    except HTTPException:
        raise

    except Exception as e:
        tracer.event(
            "http.chat_error",
            attributes={
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
        )
        raise HTTPException(
            status_code=500,
            detail=f"Agent 执行失败：{str(e)}",
        ) from e

    return {
        "session_id": session_id,
        "trace_id": tracer.trace_id,
        "request_id": tracer.request_id,
        "answer": answer,
        "last_order_id": session.memory.last_order_id,
        "pending_approval": serialize_pending_approval(session),
        "rate_limit": (
            {
                "scope": chat_rate.scope,
                "limit": chat_rate.limit,
                "count": chat_rate.count,
                "remaining": chat_rate.remaining,
                "retry_after_seconds": chat_rate.retry_after_seconds,
            }
            if chat_rate
            else None
        ),
        "created_at": time.time(),
    }
