import hashlib
import os
from dataclasses import dataclass
from typing import Optional

import redis.asyncio as redis
from fastapi import HTTPException, Request, status

from mini_agent.core.auth import CurrentUser
from mini_agent.core.config import get_settings

settings = get_settings()
CHAT_RATE_LIMIT_PER_MINUTE = int(
    settings.chat_rate_limit_per_minute
)

CHAT_RATE_LIMIT_PER_DAY = int(
   settings.chat_rate_limit_per_day
)

LOGIN_IP_RATE_LIMIT_PER_MINUTE = int(
   settings.login_ip_rate_limit_per_minute
)

LOGIN_USER_IP_RATE_LIMIT_PER_MINUTE = int(
   settings.login_user_ip_rate_limit_per_minute
)


_FIXED_WINDOW_SCRIPT = """
local current = redis.call("INCR", KEYS[1])

if current == 1 then
    redis.call("EXPIRE", KEYS[1], tonumber(ARGV[1]))
end

local ttl = redis.call("TTL", KEYS[1])

return {current, ttl}
"""


@dataclass
class RateLimitResult:
    allowed: bool
    scope: str
    limit: int
    count: int
    remaining: int
    retry_after_seconds: int


def hash_identity(identity: str) -> str:
    """
    不把 user_id / IP / username 原文直接放进 Redis key。
    """
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def get_client_ip(request: Request) -> str:
    """
    Demo 版 IP 获取。

    生产环境如果你在 Nginx / API Gateway / Load Balancer 后面，
    要正确配置 trusted proxy，再决定是否读取 X-Forwarded-For。
    不要盲目信任客户端自己传的 X-Forwarded-For。
    """
    forwarded = request.headers.get("x-forwarded-for")

    if forwarded:
        return forwarded.split(",")[0].strip()

    if request.client:
        return request.client.host

    return "unknown"


class RedisFixedWindowRateLimiter:
    def __init__(self, client: redis.Redis):
        self.client = client

    def build_key(
        self,
        *,
        scope: str,
        identity: str,
        window_seconds: int,
    ) -> str:
        identity_hash = hash_identity(identity)
        return f"rate:{scope}:{window_seconds}:{identity_hash}"

    async def hit(
        self,
        *,
        scope: str,
        identity: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        key = self.build_key(
            scope=scope,
            identity=identity,
            window_seconds=window_seconds,
        )

        count_raw, ttl_raw = await self.client.eval(
            _FIXED_WINDOW_SCRIPT,
            1,
            key,
            window_seconds,
        )

        count = int(count_raw)
        ttl = int(ttl_raw)

        if ttl < 0:
            ttl = window_seconds

        allowed = count <= limit
        remaining = max(limit - count, 0)

        return RateLimitResult(
            allowed=allowed,
            scope=scope,
            limit=limit,
            count=count,
            remaining=remaining,
            retry_after_seconds=ttl,
        )


def rate_limit_headers(result: RateLimitResult) -> dict[str, str]:
    return {
        "X-RateLimit-Scope": result.scope,
        "X-RateLimit-Limit": str(result.limit),
        "X-RateLimit-Remaining": str(result.remaining),
        "X-RateLimit-Reset": str(result.retry_after_seconds),
    }


def raise_rate_limited(result: RateLimitResult) -> None:
    headers = rate_limit_headers(result)
    headers["Retry-After"] = str(result.retry_after_seconds)

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(
            f"请求过于频繁，请 {result.retry_after_seconds} 秒后再试。"
        ),
        headers=headers,
    )


async def check_limit_or_raise(
    *,
    limiter: RedisFixedWindowRateLimiter,
    scope: str,
    identity: str,
    limit: int,
    window_seconds: int,
) -> RateLimitResult:
    result = await limiter.hit(
        scope=scope,
        identity=identity,
        limit=limit,
        window_seconds=window_seconds,
    )

    if not result.allowed:
        raise_rate_limited(result)

    return result


async def check_chat_rate_limit(
    *,
    request: Request,
    current_user: CurrentUser,
) -> RateLimitResult:
    """
    /chat 限流：
    1. 每分钟限制
    2. 每天限制

    两个都通过才允许。
    """
    limiter = RedisFixedWindowRateLimiter(
        request.app.state.redis_client
    )

    per_minute = await check_limit_or_raise(
        limiter=limiter,
        scope="chat_per_minute",
        identity=current_user.user_id,
        limit=CHAT_RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
    )

    await check_limit_or_raise(
        limiter=limiter,
        scope="chat_per_day",
        identity=current_user.user_id,
        limit=CHAT_RATE_LIMIT_PER_DAY,
        window_seconds=60 * 60 * 24,
    )

    return per_minute


async def check_login_rate_limit(
    *,
    request: Request,
    username: str,
) -> RateLimitResult:
    """
    /auth/login 限流：
    1. 同一 IP 每分钟最多 N 次
    2. 同一 username + IP 每分钟最多 N 次

    注意：无论 username 是否存在，都先做限流，避免帮助攻击者枚举用户。
    """
    limiter = RedisFixedWindowRateLimiter(
        request.app.state.redis_client
    )

    ip = get_client_ip(request)

    ip_result = await check_limit_or_raise(
        limiter=limiter,
        scope="login_ip_per_minute",
        identity=ip,
        limit=LOGIN_IP_RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
    )

    await check_limit_or_raise(
        limiter=limiter,
        scope="login_user_ip_per_minute",
        identity=f"{username}:{ip}",
        limit=LOGIN_USER_IP_RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
    )

    return ip_result
