import json
import logging
import time
import traceback
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from mini_agent.core.config import get_settings

settings = get_settings()

LOG_DIR = Path(settings.agent_log_dir)
LOG_DIR.mkdir(parents=True, exist_ok=True)
TRACE_LOG_PATH = LOG_DIR / "agent_traces.jsonl"

logger = logging.getLogger("agent_traces")
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    file_handler = logging.FileHandler(TRACE_LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console_handler)


SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "password",
    "token",
    "cookie",
    "secret",
    "access_token",
    "refresh_token",
}


def now_ms() -> int:
    return int(time.time() * 1000)


def gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def safe_preview(text: str, max_len: int = 120) -> str:
    """
    日志里不要默认记录完整用户输入 / prompt / 文档内容。
    这里只保留很短的 preview，生产环境可以直接关掉。
    """
    text = text.replace("\n", "\\n")
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def scrub(value: Any, max_str_len: int = 500) -> Any:
    """
    递归清洗日志字段，避免把 token、密钥、完整长文本打进日志。
    """

    if isinstance(value, dict):
        cleaned = {}

        for k, v in value.items():
            key = str(k).lower()

            if key in SENSITIVE_KEYS:
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = scrub(v, max_str_len=max_str_len)

        return cleaned

    if isinstance(value, list):
        return [scrub(item, max_str_len=max_str_len) for item in value[:20]]

    if isinstance(value, str):
        if len(value) > max_str_len:
            return value[:max_str_len] + "...[TRUNCATED]"
        return value

    return value


class AgentTracer:
    """
    一个轻量级本地 tracer。

    每个 /chat 请求创建一个 AgentTracer。
    同一个请求里的所有 span 共享同一个 trace_id。
    """

    def __init__(
        self,
        *,
        trace_id: Optional[str] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.trace_id = trace_id or gen_id("trace")
        self.request_id = request_id or gen_id("req")
        self.session_id = session_id
        self.user_id = user_id
        self._span_stack: list[str] = []

    @contextmanager
    def span(
        self,
        name: str,
        *,
        kind: str = "internal",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        span_id = gen_id("span")
        parent_span_id = self._span_stack[-1] if self._span_stack else None

        start_perf = time.perf_counter()
        start_time_ms = now_ms()

        self._span_stack.append(span_id)

        status = "ok"
        error = None

        try:
            yield {
                "trace_id": self.trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
            }

        except Exception as e:
            status = "error"
            error = {
                "type": type(e).__name__,
                "message": str(e),
                "stack": traceback.format_exc(limit=5),
            }
            raise

        finally:
            duration_ms = round((time.perf_counter() - start_perf) * 1000, 2)

            popped = self._span_stack.pop()
            assert popped == span_id

            self._emit({
                "type": "span",
                "trace_id": self.trace_id,
                "request_id": self.request_id,
                "session_id": self.session_id,
                "user_id": self.user_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "name": name,
                "kind": kind,
                "status": status,
                "start_time_ms": start_time_ms,
                "duration_ms": duration_ms,
                "attributes": scrub(attributes or {}),
                "error": scrub(error),
            })

    def event(
        self,
        name: str,
        *,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        parent_span_id = self._span_stack[-1] if self._span_stack else None

        self._emit({
            "type": "event",
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "parent_span_id": parent_span_id,
            "name": name,
            "time_ms": now_ms(),
            "attributes": scrub(attributes or {}),
        })

    def _emit(self, record: Dict[str, Any]) -> None:
        logger.info(json.dumps(record, ensure_ascii=False))
