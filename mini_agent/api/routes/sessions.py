import time
import uuid
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from mini_agent.agent.session import AgentSession
from mini_agent.api.deps import build_user_context
from mini_agent.core.auth import CurrentUser, get_current_user
from mini_agent.core.observability import AgentTracer
from mini_agent.core.session_store import RedisSessionStore, SessionBusyError


router = APIRouter(prefix="/sessions", tags=["sessions"])


class PendingApprovalView(BaseModel):
    tool_name: str
    args: Dict[str, Any]
    created_at: float


class MemoryResponse(BaseModel):
    session_id: str
    user_id: str
    last_order_id: Optional[str]
    pending_approval: Optional[PendingApprovalView]
    dialogue: list[Dict[str, Any]]
    tool_calls: list[Dict[str, Any]]


class DeleteSessionResponse(BaseModel):
    deleted: bool
    session_id: str


class ApprovalRequest(BaseModel):
    decision: Literal["approve", "reject"] = Field(
        ...,
        description="审批决定：approve=确认执行，reject=拒绝执行。",
    )


class ApprovalResponse(BaseModel):
    session_id: str
    trace_id: str
    request_id: str
    answer: str
    last_order_id: Optional[str]
    pending_approval: Optional[PendingApprovalView]
    created_at: float


def serialize_pending_approval(session: AgentSession) -> Optional[Dict[str, Any]]:
    pending = session.memory.pending_approval

    if pending is None:
        return None

    return {
        "tool_name": pending.tool_name,
        "args": pending.args,
        "created_at": pending.created_at,
    }


def serialize_memory(session_id: str, session: AgentSession) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "user_id": session.user.user_id,
        "last_order_id": session.memory.last_order_id,
        "pending_approval": serialize_pending_approval(session),
        "dialogue": [
            {
                "role": turn.role,
                "content": turn.content,
                "timestamp": turn.timestamp,
            }
            for turn in session.memory.dialogue
        ],
        "tool_calls": [
            {
                "tool_name": record.tool_name,
                "args": record.args,
                "result": record.result,
                "timestamp": record.timestamp,
                "approved": record.approved,
            }
            for record in session.memory.tool_calls
        ],
    }


async def load_or_create_agent_session(
    *,
    store: RedisSessionStore,
    session_id: Optional[str],
    current_user: CurrentUser,
) -> tuple[str, AgentSession, Optional[Dict[str, Any]]]:
    user_context = build_user_context(current_user)

    if session_id is None:
        new_session_id = str(uuid.uuid4())
        return new_session_id, AgentSession(user=user_context), None

    payload = await store.load(session_id)

    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"session_id 不存在或已过期：{session_id}",
        )

    if payload["user_id"] != current_user.user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="该 session 不属于当前用户。",
        )

    session = AgentSession.from_state(
        user=user_context,
        state=payload["agent_state"],
    )

    return session_id, session, payload


@router.get("/{session_id}/memory", response_model=MemoryResponse)
async def get_memory(
    session_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    store: RedisSessionStore = request.app.state.session_store
    payload = await store.load(session_id)

    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"session_id 不存在或已过期：{session_id}",
        )

    if payload["user_id"] != current_user.user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="无权查看该 session。",
        )

    user_context = build_user_context(current_user)
    session = AgentSession.from_state(
        user=user_context,
        state=payload["agent_state"],
    )

    return serialize_memory(session_id, session)


@router.delete("/{session_id}", response_model=DeleteSessionResponse)
async def delete_session(
    session_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    store: RedisSessionStore = request.app.state.session_store
    payload = await store.load(session_id)

    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"session_id 不存在或已过期：{session_id}",
        )

    if payload["user_id"] != current_user.user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="无权删除该 session。",
        )

    deleted = await store.delete(session_id)

    return {
        "deleted": bool(deleted),
        "session_id": session_id,
    }


@router.post("/{session_id}/approval", response_model=ApprovalResponse)
async def submit_session_approval(
    session_id: str,
    req: ApprovalRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    store: RedisSessionStore = request.app.state.session_store
    request_id = str(uuid.uuid4())
    tracer = AgentTracer(
        request_id=request_id,
        session_id=session_id,
        user_id=current_user.user_id,
    )

    try:
        async with store.session_lock(session_id):
            payload = await store.load(session_id)

            if payload is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"session_id 不存在或已过期：{session_id}",
                )

            if payload["user_id"] != current_user.user_id:
                raise HTTPException(
                    status_code=403,
                    detail="无权审批该 session 的待确认操作。",
                )

            user_context = build_user_context(current_user)
            session = AgentSession.from_state(
                user=user_context,
                state=payload["agent_state"],
            )

            with tracer.span(
                "http.post./sessions.approval",
                kind="server",
                attributes={
                    "session_id": session_id,
                    "user_id": current_user.user_id,
                    "username": current_user.username,
                    "decision": req.decision,
                    "has_pending_approval": (
                        session.memory.pending_approval is not None
                    ),
                    "pending_tool": (
                        session.memory.pending_approval.tool_name
                        if session.memory.pending_approval
                        else None
                    ),
                },
            ):
                answer = await run_in_threadpool(
                    session.submit_approval,
                    req.decision,
                    tracer,
                )

            await store.save(
                session_id=session_id,
                user_id=current_user.user_id,
                agent_state=session.to_state(),
                created_at=payload["created_at"],
            )

    except SessionBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    except HTTPException:
        raise

    except Exception as e:
        tracer.event(
            "http.approval_error",
            attributes={
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
        )
        raise HTTPException(
            status_code=500,
            detail=f"审批执行失败：{str(e)}",
        ) from e

    return {
        "session_id": session_id,
        "trace_id": tracer.trace_id,
        "request_id": tracer.request_id,
        "answer": answer,
        "last_order_id": session.memory.last_order_id,
        "pending_approval": serialize_pending_approval(session),
        "created_at": time.time(),
    }
