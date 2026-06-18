from typing import Any, Dict

from mini_agent.db.repositories.orders import (
    cancel_order as db_cancel_order,
    create_refund_ticket as db_create_refund_ticket,
    get_order_status as db_get_order_status,
)
from mini_agent.rag.retriever import search_policy_knowledge_base
from mini_agent.agent.schemas import UserContext


TOOLS = [
    {
        "type": "function",
        "name": "get_order_status",
        "description": "查询订单状态、物流公司、预计送达时间。用户询问订单情况时调用。",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "订单号，例如 A1001。",
                }
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "cancel_order",
        "description": (
            "取消订单。只有用户明确要求取消订单时调用。"
            "如果用户没有提供原因，reason 填“用户未提供原因”。"
            "该操作需要后端人工确认。"
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "订单号，例如 A1002。",
                },
                "reason": {
                    "type": "string",
                    "description": "取消订单原因。若用户未说明，填“用户未提供原因”。",
                },
            },
            "required": ["order_id", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "create_refund_ticket",
        "description": (
            "创建退款/退货/售后退款工单。用户申请退款、退货或售后时调用。"
            "如果用户没有提供原因，reason 填“用户未提供原因”。"
            "该操作需要后端人工确认。"
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "订单号，例如 A1001。",
                },
                "reason": {
                    "type": "string",
                    "description": "退款原因。若用户未说明，填“用户未提供原因”。",
                },
            },
            "required": ["order_id", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_policy_knowledge_base",
        "description": (
            "搜索企业政策知识库。"
            "用于回答退款政策、配送政策、会员权益、售后规则、发货时效、退款材料、退款到账时间等问题。"
            "这是只读工具，不会修改订单。"
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "用户的政策问题或需要检索的关键词。",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
]


TOOL_POLICIES = {
    "get_order_status": {
        "risk": "read",
        "requires_approval": False,
    },
    "cancel_order": {
        "risk": "high_write",
        "requires_approval": True,
    },
    "create_refund_ticket": {
        "risk": "medium_write",
        "requires_approval": True,
    },
    "search_policy_knowledge_base": {
        "risk": "read",
        "requires_approval": False,
    },
}


def execute_tool(
    user: UserContext,
    name: str,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        if name == "search_policy_knowledge_base":
            return search_policy_knowledge_base(**args)

        if name == "get_order_status":
            return db_get_order_status(
                user_id=user.user_id,
                **args,
            )

        if name == "cancel_order":
            return db_cancel_order(
                user_id=user.user_id,
                **args,
            )

        if name == "create_refund_ticket":
            return db_create_refund_ticket(
                user_id=user.user_id,
                **args,
            )

        return {
            "success": False,
            "error": "unknown_tool",
            "message": f"未知工具：{name}",
        }

    except TypeError as e:
        return {
            "success": False,
            "error": "invalid_arguments",
            "message": str(e),
        }

    except Exception as e:
        return {
            "success": False,
            "error": "tool_execution_error",
            "message": str(e),
        }
