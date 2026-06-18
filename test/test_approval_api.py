from conftest import auth_headers, login_and_get_token


def test_approval_api_approve_pending_action(client):
    token = login_and_get_token(client)

    created = client.post(
        "/chat",
        headers=auth_headers(token),
        json={
            "message": "我要取消 A1002，原因是拍错了",
        },
    )

    assert created.status_code == 200

    session_id = created.json()["session_id"]
    assert created.json()["pending_approval"] is not None

    approved = client.post(
        f"/sessions/{session_id}/approval",
        headers=auth_headers(token),
        json={
            "decision": "approve",
        },
    )

    assert approved.status_code == 200

    data = approved.json()
    assert data["pending_approval"] is None
    assert "已取消" in data["answer"]


def test_approval_api_reject_pending_action(client):
    token = login_and_get_token(client)

    created = client.post(
        "/chat",
        headers=auth_headers(token),
        json={
            "message": "我要取消 A1002，原因是拍错了",
        },
    )

    assert created.status_code == 200

    session_id = created.json()["session_id"]

    rejected = client.post(
        f"/sessions/{session_id}/approval",
        headers=auth_headers(token),
        json={
            "decision": "reject",
        },
    )

    assert rejected.status_code == 200

    data = rejected.json()
    assert data["pending_approval"] is None
    assert "拒绝" in data["answer"]


def test_approval_api_requires_owner(client):
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
            "message": "我要取消 A1002，原因是拍错了",
        },
    )

    assert created.status_code == 200
    session_id = created.json()["session_id"]

    forbidden = client.post(
        f"/sessions/{session_id}/approval",
        headers=auth_headers(bob_token),
        json={
            "decision": "approve",
        },
    )

    assert forbidden.status_code == 403


def test_approval_api_rejects_invalid_decision(client):
    token = login_and_get_token(client)

    created = client.post(
        "/chat",
        headers=auth_headers(token),
        json={
            "message": "我要取消 A1002，原因是拍错了",
        },
    )

    session_id = created.json()["session_id"]

    response = client.post(
        f"/sessions/{session_id}/approval",
        headers=auth_headers(token),
        json={
            "decision": "maybe",
        },
    )

    assert response.status_code == 422
