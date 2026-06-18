# tests/test_auth.py

from conftest import auth_headers, login_and_get_token


def test_login_success_and_me(client):
    token = login_and_get_token(
        client,
        username="alice",
        password="alice123",
    )

    response = client.get(
        "/auth/me",
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    data = response.json()
    assert data["user_id"] == "user_001"
    assert data["username"] == "alice"
    assert data["role"] == "customer"


def test_login_wrong_password(client):
    response = client.post(
        "/auth/login",
        data={
            "username": "alice",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401


def test_chat_requires_token(client):
    response = client.post(
        "/chat",
        json={
            "message": "帮我查一下 A1002",
        },
    )

    assert response.status_code == 401
