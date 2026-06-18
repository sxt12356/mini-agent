# tests/test_order_repository.py

from mini_agent.db.repositories.orders import get_order_status


def test_alice_can_access_own_order():
    result = get_order_status(
        user_id="user_001",
        order_id="A1002",
    )

    assert result["success"] is True
    assert result["order_id"] == "A1002"
    assert result["status"] == "processing"


def test_alice_cannot_access_bob_order():
    result = get_order_status(
        user_id="user_001",
        order_id="B2001",
    )

    assert result["success"] is False
    assert result["error"] == "permission_denied"
