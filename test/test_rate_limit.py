# tests/test_rate_limit.py

from conftest import auth_headers, login_and_get_token


def test_login_rate_limit_by_username_and_ip(client):
    """
    conftest 里设置：
    LOGIN_USER_IP_RATE_LIMIT_PER_MINUTE=2

    所以同一个 username + IP：
    前 2 次错误登录返回 401
    第 3 次返回 429
    """
    for _ in range(2):
        response = client.post(
            "/auth/login",
            data={
                "username": "alice",
                "password": "wrong-password",
            },
        )
        assert response.status_code == 401

    blocked = client.post(
        "/auth/login",
        data={
            "username": "alice",
            "password": "wrong-password",
        },
    )

    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_chat_rate_limit_per_minute(client):
    """
    conftest 里设置：
    CHAT_RATE_LIMIT_PER_MINUTE=2

    所以同一个用户：
    前 2 次 /chat 成功
    第 3 次 /chat 返回 429
    """
    token = login_and_get_token(client)

    for _ in range(2):
        response = client.post(
            "/chat",
            headers=auth_headers(token),
            json={
                "message": "帮我查一下 A1002",
            },
        )
        assert response.status_code == 200

    blocked = client.post(
        "/chat",
        headers=auth_headers(token),
        json={
            "message": "再查一次 A1002",
        },
    )

    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
