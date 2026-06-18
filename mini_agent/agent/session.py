import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional
from dotenv import load_dotenv
from openai import OpenAI
from mini_agent.agent.prompts import BASE_SYSTEM_PROMPT

from mini_agent.agent.schemas import (
    AgentMemory,
    Decision,
    DialogueTurn,
    PendingApproval,
    ToolCallRecord,
    UserContext,
)
from mini_agent.agent.tools import TOOLS, TOOL_POLICIES, execute_tool
from mini_agent.core.config import get_settings
from mini_agent.core.observability import AgentTracer, safe_preview

settings = get_settings()
client = OpenAI(api_key=settings.openai_api_key)
MODEL = settings.openai_model



# =========================
# 7. Responses API 辅助函数
# =========================

def response_output_to_input_items(output_items: list[Any]) -> list[Dict[str, Any]]:
    """
    把 response.output 转成下一轮 input 可接受的 dict。

    关键：
    要保留模型原始 function_call。
    否则后面追加 function_call_output 时，call_id 可能对不上。
    """
    converted = []

    for item in output_items:
        if hasattr(item, "model_dump"):
            converted.append(item.model_dump(exclude_none=True))
        elif isinstance(item, dict):
            converted.append(item)
        else:
            raise TypeError(f"Unsupported response output item: {type(item)}")

    return converted


def is_function_call(item: Any) -> bool:
    if isinstance(item, dict):
        return item.get("type") == "function_call"

    return getattr(item, "type", None) == "function_call"


def read_function_call(item: Any) -> tuple[str, Dict[str, Any], str]:
    if isinstance(item, dict):
        name = item["name"]
        raw_args = item.get("arguments") or "{}"
        call_id = item["call_id"]
    else:
        name = item.name
        raw_args = item.arguments or "{}"
        call_id = item.call_id

    return name, json.loads(raw_args), call_id


def make_function_call_output(call_id: str, output: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": json.dumps(output, ensure_ascii=False),
    }
def dialogue_turn_to_dict(turn: DialogueTurn) -> Dict[str, Any]:
    return {
        "role": turn.role,
        "content": turn.content,
        "timestamp": turn.timestamp,
    }


def dialogue_turn_from_dict(data: Dict[str, Any]) -> DialogueTurn:
    return DialogueTurn(
        role=data["role"],
        content=data["content"],
        timestamp=float(data["timestamp"]),
    )


def pending_approval_to_dict(
    pending: Optional[PendingApproval],
) -> Optional[Dict[str, Any]]:
    if pending is None:
        return None

    return {
        "call_id": pending.call_id,
        "tool_name": pending.tool_name,
        "args": pending.args,
        "created_at": pending.created_at,
    }


def pending_approval_from_dict(
    data: Optional[Dict[str, Any]],
) -> Optional[PendingApproval]:
    if data is None:
        return None

    return PendingApproval(
        call_id=data["call_id"],
        tool_name=data["tool_name"],
        args=data["args"],
        created_at=float(data["created_at"]),
    )


def tool_call_record_to_dict(record: ToolCallRecord) -> Dict[str, Any]:
    return {
        "tool_name": record.tool_name,
        "args": record.args,
        "result": record.result,
        "timestamp": record.timestamp,
        "approved": record.approved,
    }


def tool_call_record_from_dict(data: Dict[str, Any]) -> ToolCallRecord:
    return ToolCallRecord(
        tool_name=data["tool_name"],
        args=data["args"],
        result=data["result"],
        timestamp=float(data["timestamp"]),
        approved=data.get("approved"),
    )


def memory_to_dict(memory: AgentMemory) -> Dict[str, Any]:
    return {
        "dialogue": [
            dialogue_turn_to_dict(turn)
            for turn in memory.dialogue
        ],
        "tool_calls": [
            tool_call_record_to_dict(record)
            for record in memory.tool_calls
        ],
        "pending_approval": pending_approval_to_dict(memory.pending_approval),
        "last_order_id": memory.last_order_id,
    }


def memory_from_dict(data: Dict[str, Any]) -> AgentMemory:
    return AgentMemory(
        dialogue=[
            dialogue_turn_from_dict(turn)
            for turn in data.get("dialogue", [])
        ],
        tool_calls=[
            tool_call_record_from_dict(record)
            for record in data.get("tool_calls", [])
        ],
        pending_approval=pending_approval_from_dict(
            data.get("pending_approval")
        ),
        last_order_id=data.get("last_order_id"),
    )

class AgentSession:
    def __init__(self, user: UserContext):
        self.user = user
        self.memory = AgentMemory()
        self.input_items: list[Dict[str, Any]] = []
    
    def to_state(self) -> Dict[str, Any]:
        """
        把当前 AgentSession 转成可保存到 Redis 的 JSON state。
        """
        return {
            "memory": memory_to_dict(self.memory),
            "input_items": self.input_items,
        }

    @classmethod
    def from_state(
        cls,
        user: UserContext,
        state: Dict[str, Any],
    ) -> "AgentSession":
        """
        从 Redis 里的 JSON state 还原 AgentSession。
        """
        session = cls(user=user)
        session.memory = memory_from_dict(state.get("memory", {}))
        session.input_items = state.get("input_items", [])
        return session

    def send(self, user_message: str, tracer: Optional[AgentTracer] = None) -> str:
        tracer = tracer or AgentTracer(
            session_id=None,
            user_id=self.user.user_id,
        )

        with tracer.span(
            "agent.send",
            attributes={
                "message_preview": safe_preview(user_message),
                "has_pending_approval": self.memory.pending_approval is not None,
                "last_order_id": self.memory.last_order_id,
            },
        ):
            self.memory.dialogue.append(
                DialogueTurn(role="user", content=user_message, timestamp=time.time())
            )

            if self.memory.pending_approval:
                return self._handle_pending_approval(user_message, tracer=tracer)

            self.input_items.append({
                "role": "user",
                "content": user_message,
            })

            return self._run_loop(tracer=tracer)

    def submit_approval(
        self,
        decision: Decision,
        tracer: Optional[AgentTracer] = None,
    ) -> str:
        """
        结构化审批入口，用于 POST /sessions/{session_id}/approval。
        """
        tracer = tracer or AgentTracer(
            session_id=None,
            user_id=self.user.user_id,
        )

        with tracer.span(
            "agent.submit_approval",
            attributes={
                "decision": decision,
                "has_pending_approval": self.memory.pending_approval is not None,
                "pending_tool": self.memory.pending_approval.tool_name
                if self.memory.pending_approval
                else None,
            },
        ):
            if self.memory.pending_approval is None:
                answer = "当前没有待确认操作。"

                self.memory.dialogue.append(
                    DialogueTurn(
                        role="assistant",
                        content=answer,
                        timestamp=time.time(),
                    )
                )

                return answer

            self.memory.dialogue.append(
                DialogueTurn(
                    role="user",
                    content=f"[approval:{decision}]",
                    timestamp=time.time(),
                )
            )

            approval_text = "确认" if decision == "approve" else "拒绝"
            return self._handle_pending_approval(approval_text, tracer=tracer)

    def _handle_pending_approval(
        self,
        user_message: str,
        tracer: AgentTracer,
    ) -> str:
        with tracer.span(
            "approval.handle",
            attributes={
                "message_preview": safe_preview(user_message),
                "pending_tool": self.memory.pending_approval.tool_name
                if self.memory.pending_approval
                else None,
            },
        ):
            decision = parse_human_decision(user_message)

            tracer.event(
                "approval.decision_parsed",
                attributes={
                    "decision": decision,
                },
            )

            if decision is None:
                return (
                    "当前有一个待确认操作。\n"
                    "请回复「确认」执行，或回复「拒绝」放弃。"
                )

            pending = self.memory.pending_approval
            self.memory.pending_approval = None

            assert pending is not None

            if decision == "reject":
                result = {
                    "success": False,
                    "approved": False,
                    "tool_name": pending.tool_name,
                    "args": pending.args,
                    "message": "用户拒绝执行该操作。",
                }

                self._record_tool_call(
                    tool_name=pending.tool_name,
                    args=pending.args,
                    result=result,
                    approved=False,
                )

            else:
                with tracer.span(
                    f"tool.execute.{pending.tool_name}",
                    kind="tool",
                    attributes={
                        "tool_name": pending.tool_name,
                        "args": pending.args,
                        "approved": True,
                    },
                ):
                    raw_result = execute_tool(
                        user=self.user,
                        name=pending.tool_name,
                        args=pending.args,
                    )

                self._record_tool_call(
                    tool_name=pending.tool_name,
                    args=pending.args,
                    result=raw_result,
                    approved=True,
                )

                result = {
                    "approved": True,
                    "tool_name": pending.tool_name,
                    "result": raw_result,
                }

            self.input_items.append(
                make_function_call_output(
                    call_id=pending.call_id,
                    output=result,
                )
            )

            return self._run_loop(tracer=tracer)

    def _run_loop(
        self,
        max_steps: int = 6,
        tracer: Optional[AgentTracer] = None,
    ) -> str:
        tracer = tracer or AgentTracer(user_id=self.user.user_id)

        with tracer.span(
            "agent.loop",
            attributes={
                "max_steps": max_steps,
                "input_items_count": len(self.input_items),
                "last_order_id": self.memory.last_order_id,
            },
        ):
            for step in range(max_steps):
                with tracer.span(
                    "llm.responses.create",
                    kind="llm",
                    attributes={
                        "model": MODEL,
                        "step": step,
                        "tools_count": len(TOOLS),
                        "input_items_count": len(self.input_items),
                    },
                ):
                    response = client.responses.create(
                        model=MODEL,
                        instructions=self._build_instructions(),
                        input=self.input_items,
                        tools=TOOLS,
                        parallel_tool_calls=False,
                    )

                self.input_items.extend(
                    response_output_to_input_items(response.output)
                )

                tool_calls = [
                    item for item in response.output
                    if is_function_call(item)
                ]

                tracer.event(
                    "llm.output_received",
                    attributes={
                        "step": step,
                        "tool_call_count": len(tool_calls),
                        "output_text_preview": safe_preview(response.output_text or ""),
                    },
                )

                if not tool_calls:
                    answer = response.output_text or "好的。"

                    self.memory.dialogue.append(
                        DialogueTurn(
                            role="assistant",
                            content=answer,
                            timestamp=time.time(),
                        )
                    )

                    tracer.event(
                        "agent.final_answer",
                        attributes={
                            "answer_preview": safe_preview(answer),
                        },
                    )

                    return answer

                for tool_call in tool_calls:
                    tool_name, args, call_id = read_function_call(tool_call)

                    tracer.event(
                        "tool.call_requested",
                        attributes={
                            "step": step,
                            "tool_name": tool_name,
                            "args": args,
                            "call_id": call_id,
                        },
                    )

                    print(f"[step={step}] tool_call: {tool_name}({args})")

                    policy = TOOL_POLICIES.get(tool_name, {
                        "risk": "unknown",
                        "requires_approval": True,
                    })

                    if policy["requires_approval"]:
                        self.memory.pending_approval = PendingApproval(
                            call_id=call_id,
                            tool_name=tool_name,
                            args=args,
                            created_at=time.time(),
                        )

                        approval_message = build_approval_message(tool_name, args)

                        self.memory.dialogue.append(
                            DialogueTurn(
                                role="assistant",
                                content=approval_message,
                                timestamp=time.time(),
                            )
                        )

                        tracer.event(
                            "tool.pending_approval_created",
                            attributes={
                                "tool_name": tool_name,
                                "args": args,
                                "risk": policy["risk"],
                                "approval_message_preview": safe_preview(approval_message),
                            },
                        )

                        return approval_message

                    with tracer.span(
                        f"tool.execute.{tool_name}",
                        kind="tool",
                        attributes={
                            "tool_name": tool_name,
                            "args": args,
                            "risk": policy["risk"],
                        },
                    ):
                        result = execute_tool(
                            user=self.user,
                            name=tool_name,
                            args=args,
                        )

                    tracer.event(
                        "tool.result_received",
                        attributes={
                            "tool_name": tool_name,
                            "success": result.get("success"),
                            "error": result.get("error"),
                            "message": result.get("message"),
                        },
                    )

                    self._record_tool_call(
                        tool_name=tool_name,
                        args=args,
                        result=result,
                        approved=None,
                    )

                    self.input_items.append(
                        make_function_call_output(
                            call_id=call_id,
                            output=result,
                        )
                    )

            tracer.event(
                "agent.max_steps_exceeded",
                attributes={
                    "max_steps": max_steps,
                },
            )

            return "任务执行步数过多，已停止。"

    def _record_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Dict[str, Any],
        approved: Optional[bool],
    ) -> None:
        self.memory.tool_calls.append(
            ToolCallRecord(
                tool_name=tool_name,
                args=args,
                result=result,
                timestamp=time.time(),
                approved=approved,
            )
        )

        order_id = result.get("order_id") or args.get("order_id")

        # 只要不是越权/不存在，就可以更新 last_order_id。
        # 例如 already_shipped_or_delivered 虽然 success=False，
        # 但这个订单确实属于当前用户，仍然可以作为上下文里的“它”。
        if order_id and result.get("error") != "permission_denied":
            self.memory.last_order_id = order_id

        order_id = args.get("order_id")

        if order_id and order_id in self.user.allowed_order_ids:
            self.memory.last_order_id = order_id

    def _build_instructions(self) -> str:
        return BASE_SYSTEM_PROMPT + "\n\n" + self._memory_summary_for_model()

    def _memory_summary_for_model(self) -> str:
        recent_calls = self.memory.tool_calls[-5:]

        lines = [
            "当前用户记忆：",
            f"- user_id: {self.user.user_id}",
            f"- last_order_id: {self.memory.last_order_id or '无'}",
            "- 最近工具调用：",
        ]

        if not recent_calls:
            lines.append("  无")
        else:
            for idx, record in enumerate(recent_calls, start=1):
                result_summary = {
                    key: record.result.get(key)
                    for key in [
                        "success",
                        "order_id",
                        "status",
                        "carrier",
                        "eta",
                        "ticket_id",
                        "error",
                        "message",
                    ]
                    if key in record.result
                }

                lines.append(
                    f"  {idx}. {record.tool_name}"
                    f" args={json.dumps(record.args, ensure_ascii=False)}"
                    f" result={json.dumps(result_summary, ensure_ascii=False)}"
                    f" approved={record.approved}"
                )

        lines.append("注意：记忆只用于理解上下文，不能绕过后端权限检查。")

        return "\n".join(lines)

    def debug_memory(self) -> None:
        print("\n========== MEMORY ==========")
        print(f"last_order_id: {self.memory.last_order_id}")
        print(f"pending_approval: {self.memory.pending_approval}")
        print("tool_calls:")
        for record in self.memory.tool_calls:
            print(record)
        print("============================\n")


# =========================
# 9. CLI 入口
# =========================

if __name__ == "__main__":
    session = AgentSession(user=CURRENT_USER)

    print("售后 Agent 已启动。")
    print("可测试：")
    print("1. 帮我查一下 A1001")
    print("2. 帮我取消它，原因是不想要了")
    print("3. 确认")
    print("4. 帮我给 A1003 申请退款，原因是质量问题")
    print("输入 /memory 查看记忆，输入 exit 退出。")

    while True:
        user_input = input("\nUser: ").strip()

        if user_input.lower() in {"exit", "quit"}:
            break

        if user_input == "/memory":
            session.debug_memory()
            continue

        answer = session.send(user_input)
        print(f"Agent: {answer}")
