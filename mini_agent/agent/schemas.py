from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional


Decision = Literal["approve", "reject"]


@dataclass
class UserContext:
    user_id: str
    allowed_order_ids: set[str] = field(default_factory=set)
    role: str = "customer"


@dataclass
class PendingApproval:
    call_id: str
    tool_name: str
    args: Dict[str, Any]
    created_at: float


@dataclass
class DialogueTurn:
    role: Literal["user", "assistant"]
    content: str
    timestamp: float


@dataclass
class ToolCallRecord:
    tool_name: str
    args: Dict[str, Any]
    result: Dict[str, Any]
    timestamp: float
    approved: Optional[bool] = None


@dataclass
class AgentMemory:
    dialogue: list[DialogueTurn] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    pending_approval: Optional[PendingApproval] = None
    last_order_id: Optional[str] = None