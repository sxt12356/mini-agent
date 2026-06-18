# tests/conftest.py

import os
import sys
import time
from pathlib import Path

import pytest
import redis as sync_redis
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# =========================
# 1. 测试环境变量：必须在 import api/database/auth 之前设置
# =========================

os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["OPENAI_MODEL"] = "gpt-5"
os.environ["EMBEDDING_MODEL"] = "text-embedding-3-small"

os.environ[
    "DATABASE_URL"
] = "postgresql+psycopg://mini_user:mini_password@localhost:5432/mini_agent"

# 本地测试建议使用 Redis DB 15，避免清掉开发数据。
os.environ["REDIS_URL"] = "redis://localhost:6379/15"

os.environ["JWT_SECRET_KEY"] = "test-secret-key-with-at-least-32-bytes"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"

# 为了方便测试限流，把阈值调小。
os.environ["CHAT_RATE_LIMIT_PER_MINUTE"] = "2"
os.environ["CHAT_RATE_LIMIT_PER_DAY"] = "100"
os.environ["LOGIN_IP_RATE_LIMIT_PER_MINUTE"] = "20"
os.environ["LOGIN_USER_IP_RATE_LIMIT_PER_MINUTE"] = "2"


# =========================
# 2. 每个测试前重置 DB + Redis
# =========================

@pytest.fixture(autouse=True)
def reset_db_and_redis():
    """
    每个测试都从干净状态开始。
    """
    from mini_agent.db.init_db import create_extensions, create_tables, reset_demo_data

    create_extensions()
    create_tables()
    reset_demo_data()

    redis_client = sync_redis.Redis.from_url(
        os.environ["REDIS_URL"],
        decode_responses=True,
    )
    redis_client.flushdb()

    yield

    redis_client.flushdb()


# =========================
# 3. Mock AgentSession.send，避免 CI 调真实 OpenAI
# =========================

@pytest.fixture
def client(monkeypatch):
    """
    FastAPI TestClient。

    这里 mock 掉 AgentSession.send()：
    - 不调用真实 LLM
    - 仍然走真实 JWT / Redis / RateLimit / Session 保存逻辑
    """
    from mini_agent.agent.schemas import PendingApproval
    from mini_agent.agent.session import AgentSession

    def fake_send(self, user_message: str, tracer=None) -> str:
        text = user_message.strip()

        if text == "确认" and self.memory.pending_approval:
            self.memory.pending_approval = None
            self.memory.last_order_id = "A1002"
            return "订单 A1002 已取消。"

        if "A1002" in text:
            self.memory.last_order_id = "A1002"

        if "取消" in text:
            self.memory.last_order_id = "A1002"
            self.memory.pending_approval = PendingApproval(
                call_id="mock-call-id",
                tool_name="cancel_order",
                args={
                    "order_id": "A1002",
                    "reason": "测试原因",
                },
                created_at=time.time(),
            )
            return "检测到高风险操作：取消订单 A1002。\n请回复「确认」执行，或回复「拒绝」放弃。"

        return f"MOCK_ANSWER: {text}"

    monkeypatch.setattr(AgentSession, "send", fake_send)

    def fake_submit_approval(self, decision: str, tracer=None) -> str:
        if self.memory.pending_approval is None:
            return "当前没有待确认操作。"

        if decision == "reject":
            self.memory.pending_approval = None
            return "已拒绝执行该操作。"

        self.memory.pending_approval = None
        self.memory.last_order_id = "A1002"
        return "订单 A1002 已取消。"

    monkeypatch.setattr(
        AgentSession,
        "submit_approval",
        fake_submit_approval,
    )

    from main import app

    with TestClient(app) as test_client:
        yield test_client


# =========================
# 4. 登录 helper
# =========================

def login_and_get_token(
    client: TestClient,
    username: str = "alice",
    password: str = "alice123",
) -> str:
    response = client.post(
        "/auth/login",
        data={
            "username": username,
            "password": password,
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()
    return data["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
    }
