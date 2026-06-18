import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    embedding_model: str
    embedding_dim: int

    redis_url: str
    session_ttl_seconds: int

    database_url: str

    jwt_secret_key: str
    jwt_algorithm: str
    access_token_expire_minutes: int

    agent_log_dir: str

    chat_rate_limit_per_minute: int
    chat_rate_limit_per_day: int
    login_ip_rate_limit_per_minute: int
    login_user_ip_rate_limit_per_minute: int


@lru_cache
def get_settings() -> Settings:
    load_dotenv()

    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        embedding_dim=int(os.getenv("EMBEDDING_DIM", "1536")),

        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "604800")),

        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://mini_user:mini_password@localhost:5432/mini_agent",
        ),

        jwt_secret_key=os.getenv("JWT_SECRET_KEY", "dev-only-secret-change-me"),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        access_token_expire_minutes=int(
            os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
        ),

        agent_log_dir=os.getenv("AGENT_LOG_DIR", "logs"),

        chat_rate_limit_per_minute=int(
            os.getenv("CHAT_RATE_LIMIT_PER_MINUTE", "20")
        ),
        chat_rate_limit_per_day=int(
            os.getenv("CHAT_RATE_LIMIT_PER_DAY", "500")
        ),
        login_ip_rate_limit_per_minute=int(
            os.getenv("LOGIN_IP_RATE_LIMIT_PER_MINUTE", "20")
        ),
        login_user_ip_rate_limit_per_minute=int(
            os.getenv("LOGIN_USER_IP_RATE_LIMIT_PER_MINUTE", "5")
        ),
    )
