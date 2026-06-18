import uuid
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from mini_agent.db.session import db_session
from mini_agent.db.models import Order, RefundTicket, utc_now


def order_to_dict(order: Order) -> Dict[str, Any]:
    return {
        "order_id": order.order_id,
        "user_id": order.user_id,
        "status": order.status,
        "carrier": order.carrier,
        "eta": order.eta,
    }


def get_order_for_user(
    db: Session,
    *,
    user_id: str,
    order_id: str,
) -> Optional[Order]:
    stmt = select(Order).where(
        Order.order_id == order_id,
        Order.user_id == user_id,
    )

    return db.execute(stmt).scalar_one_or_none()


def get_order_status(
    *,
    user_id: str,
    order_id: str,
) -> Dict[str, Any]:
    with db_session() as db:
        order = get_order_for_user(
            db,
            user_id=user_id,
            order_id=order_id,
        )

        if order is None:
            return {
                "success": False,
                "order_id": order_id,
                "error": "permission_denied",
                "message": "当前用户无权访问该订单，或订单不存在。",
            }

        return {
            "success": True,
            **order_to_dict(order),
        }


def cancel_order(
    *,
    user_id: str,
    order_id: str,
    reason: str,
) -> Dict[str, Any]:
    with db_session() as db:
        order = get_order_for_user(
            db,
            user_id=user_id,
            order_id=order_id,
        )

        if order is None:
            return {
                "success": False,
                "order_id": order_id,
                "error": "permission_denied",
                "message": "当前用户无权访问该订单，或订单不存在。",
            }

        if order.status == "cancelled":
            return {
                "success": False,
                "order_id": order_id,
                "error": "already_cancelled",
                "message": "订单已经取消过了。",
            }

        if order.status in {"shipped", "delivered"}:
            return {
                "success": False,
                "order_id": order_id,
                "error": "already_shipped_or_delivered",
                "message": "订单已发货或已签收，不能直接取消，建议申请退款/售后。",
            }

        order.status = "cancelled"
        order.updated_at = utc_now()

        return {
            "success": True,
            "order_id": order_id,
            "cancelled": True,
            "reason": reason,
            "message": "订单已取消。",
        }


def create_refund_ticket(
    *,
    user_id: str,
    order_id: str,
    reason: str,
) -> Dict[str, Any]:
    with db_session() as db:
        order = get_order_for_user(
            db,
            user_id=user_id,
            order_id=order_id,
        )

        if order is None:
            return {
                "success": False,
                "order_id": order_id,
                "error": "permission_denied",
                "message": "当前用户无权访问该订单，或订单不存在。",
            }

        if order.status == "processing":
            return {
                "success": False,
                "order_id": order_id,
                "error": "not_eligible_for_refund",
                "message": "订单还未发货，建议直接取消订单，而不是申请退款。",
            }

        if order.status == "cancelled":
            return {
                "success": False,
                "order_id": order_id,
                "error": "already_cancelled",
                "message": "订单已取消，无需再创建退款工单。",
            }

        if order.status not in {"shipped", "delivered"}:
            return {
                "success": False,
                "order_id": order_id,
                "error": "unsupported_order_status",
                "message": f"当前订单状态为 {order.status}，暂不支持申请退款。",
            }

        ticket_id = f"R-{order_id}-{uuid.uuid4().hex[:8].upper()}"

        ticket = RefundTicket(
            ticket_id=ticket_id,
            order_id=order.order_id,
            user_id=user_id,
            reason=reason,
            status="created",
        )

        db.add(ticket)

        return {
            "success": True,
            "ticket_id": ticket_id,
            "order_id": order_id,
            "reason": reason,
            "status": "created",
            "message": "退款工单已创建。",
        }