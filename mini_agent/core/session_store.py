import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

import redis.asyncio as redis

from mini_agent.core.config import get_settings

settings = get_settings()
REDIS_URL = settings.redis_url
SESSION_TTL_SECONDS = settings.session_ttl_seconds



class SessionNotFoundError(Exception):
    pass


class SessionOwnershipError(Exception):
    pass


class SessionBusyError(Exception):
    pass


def create_redis_client() -> redis.Redis:
    """
    创建 Redis async client。

    decode_responses=True 会让 Redis 返回 str，而不是 bytes。
    """
    return redis.from_url(
        REDIS_URL,
        decode_responses=True,
    )


_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class RedisSessionStore:
    def __init__(self, client: redis.Redis):
        self.client = client

    def session_key(self, session_id: str) -> str:
        return f"agent:session:{session_id}"

    def lock_key(self, session_id: str) -> str:
        return f"agent:session_lock:{session_id}"

    async def ping(self) -> bool:
        return bool(await self.client.ping())

    async def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        raw = await self.client.get(self.session_key(session_id))

        if raw is None:
            return None

        return json.loads(raw)

    async def save(
        self,
        *,
        session_id: str,
        user_id: str,
        agent_state: Dict[str, Any],
        created_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        now = time.time()

        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": created_at or now,
            "updated_at": now,
            "agent_state": agent_state,
        }

        await self.client.set(
            self.session_key(session_id),
            json.dumps(payload, ensure_ascii=False),
            ex=SESSION_TTL_SECONDS,
        )

        return payload

    async def delete(self, session_id: str) -> bool:
        deleted = await self.client.delete(self.session_key(session_id))
        return deleted > 0

    async def ttl(self, session_id: str) -> int:
        return int(await self.client.ttl(self.session_key(session_id)))

    @asynccontextmanager
    async def session_lock(
        self,
        session_id: str,
        *,
        lock_ttl_ms: int = 120_000,
        wait_timeout_s: float = 10.0,
        retry_interval_s: float = 0.05,
    ) -> AsyncIterator[None]:
        """
        Redis 分布式锁。

        作用：
        同一个 session_id 同一时间只允许一个请求修改 memory/input_items。

        注意：
        这是 demo 级实现。生产环境可以加自动续租 watchdog，
        防止超长 LLM 请求超过 lock_ttl_ms 后锁过期。
        """
        key = self.lock_key(session_id)
        token = uuid.uuid4().hex
        deadline = time.monotonic() + wait_timeout_s

        acquired = False

        while time.monotonic() < deadline:
            ok = await self.client.set(
                key,
                token,
                nx=True,
                px=lock_ttl_ms,
            )

            if ok:
                acquired = True
                break

            await asyncio.sleep(retry_interval_s)

        if not acquired:
            raise SessionBusyError(
                f"session 正在处理中，请稍后重试：{session_id}"
            )

        try:
            yield

        finally:
            await self.client.eval(
                _RELEASE_LOCK_SCRIPT,
                1,
                key,
                token,
            )
    