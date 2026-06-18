# tests/test_chat_api.py

from conftest import auth_headers, login_and_get_token


def test_chat_success_with_token(client):
    token = login_and_get_token(client)

    response = client.post(
        "/chat",
        headers=auth_headers(token),
        json={
            "message": "帮我查一下 A1002",
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["session_id"]
    assert data["trace_id"]
    assert data["answer"] == "MOCK_ANSWER: 帮我查一下 A1002"
    assert data["last_order_id"] == "A1002"


def test_chat_creates_pending_approval(client):
    token = login_and_get_token(client)

    response = client.post(
        "/chat",
        headers=auth_headers(token),
        json={
            "message": "我要取消 A1002，原因是拍错了",
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["pending_approval"] is not None
    assert data["pending_approval"]["tool_name"] == "cancel_order"
    assert data["pending_approval"]["args"]["order_id"] == "A1002"


def test_confirm_pending_approval_across_session(client):
    token = login_and_get_token(client)

    first = client.post(
        "/chat",
        headers=auth_headers(token),
        json={
            "message": "我要取消 A1002，原因是拍错了",
        },
    )

    assert first.status_code == 200
    session_id = first.json()["session_id"]
    assert first.json()["pending_approval"] is not None

    second = client.post(
        "/chat",
        headers=auth_headers(token),
        json={
            "session_id": session_id,
            "message": "确认",
        },
    )

    assert second.status_code == 200

    data = second.json()
    assert data["pending_approval"] is None
    assert "已取消" in data["answer"]


def test_session_memory_owner_only(client):
    alice_token = login_and_get_token(
        client,
        username="alice",
        password="alice123",
    )

    bob_token = login_and_get_token(
        client,
        username="bob",
        password="bob123",
    )

    created = client.post(
        "/chat",
        headers=auth_headers(alice_token),
        json={
            "message": "帮我查一下 A1002",
        },
    )

    assert created.status_code == 200
    session_id = created.json()["session_id"]

    forbidden = client.get(
        f"/sessions/{session_id}/memory",
        headers=auth_headers(bob_token),
    )

    assert forbidden.status_code == 403
