# E-commerce Support AI Agent

一个电商售后 AI Agent 后端系统，支持订单查询、取消订单、退款工单、政策知识库问答、多轮记忆、人工审批、权限控制、RAG 检索、Tracing、限流、自动化测试和 Docker 部署。

## Overview

本项目不是普通 Chatbot，而是一个接近真实业务场景的 AI Agent 系统。

它可以：

- 查询订单状态
- 处理取消订单请求
- 创建退款工单
- 基于企业政策知识库回答退款、配送、会员权益等问题
- 支持多轮上下文，例如“取消刚才那个订单”
- 对高风险写操作执行 human-in-the-loop 人工确认
- 使用 Redis 保存 Agent session memory
- 使用 Postgres 保存订单、用户和退款工单
- 使用 Postgres + pgvector 保存知识库向量索引
- 使用 JWT 做登录鉴权
- 使用 Redis 做限流
- 使用 trace_id 记录 LLM 调用、工具调用、RAG 检索和审批流程
- 使用 pytest + GitHub Actions 做自动化测试

## Demo Flow

推荐演示流程：

```text
1. 登录 alice / alice123
2. 输入：帮我查一下 A1002
3. 输入：那它应该退款还是取消？
4. 输入：我要取消它，原因是拍错了
5. 页面出现「确认执行」和「拒绝」按钮
6. 点击「确认执行」
7. Agent 返回订单已取消
8. 查看 Memory
9. 根据 trace_id 查看完整执行链路
```

## Features

### Agent

- 手写 Agent loop
- Function calling / tool calling
- Tool schema 管理
- Tool router
- Multi-turn memory
- Human-in-the-loop
- Structured approval API
- Tool policies

### RAG

- 文档结构化 chunking
- source / section / heading_path metadata
- OpenAI embeddings
- Postgres + pgvector 检索
- cosine similarity top-k search
- source citation
- 低相关度拒答机制

### Backend

- FastAPI API 服务
- JWT Bearer 鉴权
- Redis-backed session store
- Redis rate limiting
- Postgres business data
- SQLAlchemy repository layer
- Trace logging
- Docker Compose 部署

### Testing

- pytest 自动化测试
- FastAPI TestClient
- Mock LLM 调用
- JWT 测试
- Redis session 测试
- Postgres 权限测试
- Rate limit 测试
- Approval API 测试
- RAG chunking / pgvector 测试

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python |
| API | FastAPI |
| LLM | OpenAI Responses API |
| Tool Calling | Function tools |
| RAG | OpenAI Embeddings + pgvector |
| Database | PostgreSQL |
| Vector Search | pgvector |
| Session | Redis |
| Auth | JWT Bearer |
| ORM | SQLAlchemy |
| Testing | pytest |
| Deployment | Docker Compose |
| Frontend Demo | HTML + CSS + JavaScript |

---

## System Architecture

```mermaid
flowchart TD
    U[User / Browser] --> FE[Frontend Demo]

    FE -->|Login| AUTH[/POST /auth/login/]
    FE -->|Chat| CHAT[/POST /chat/]
    FE -->|Approve or Reject| APPROVAL[/POST /sessions/{id}/approval/]
    FE -->|Debug| MEMORY[/GET /sessions/{id}/memory/]

    AUTH --> JWT[JWT Auth]
    CHAT --> API[FastAPI API Layer]
    APPROVAL --> API
    MEMORY --> API

    API --> AGENT[AgentSession]

    AGENT --> MEMORY_STATE[Agent Memory]
    MEMORY_STATE --> REDIS[(Redis Session Store)]

    AGENT --> TOOLS[Tool Router]

    TOOLS --> ORDER_TOOL[Order Tools]
    ORDER_TOOL --> PG[(Postgres Business DB)]

    TOOLS --> RAG_TOOL[RAG Policy Search]
    RAG_TOOL --> PGVECTOR[(Postgres + pgvector)]

    AGENT --> LLM[OpenAI Responses API]

    API --> TRACE[Trace Logs]
    AGENT --> TRACE
    TOOLS --> TRACE
    RAG_TOOL --> TRACE
```

---

## Agent Execution Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API as FastAPI
    participant Agent as AgentSession
    participant LLM as OpenAI Model
    participant Tool as Tool Router
    participant DB as Postgres / pgvector
    participant Redis

    User->>Frontend: 输入消息
    Frontend->>API: POST /chat
    API->>Redis: 加载 session state
    Redis-->>API: memory / input_items
    API->>Agent: session.send(message)
    Agent->>LLM: messages + tools
    LLM-->>Agent: function_call
    Agent->>Tool: execute_tool(name, args)
    Tool->>DB: 查询订单 / 检索知识库
    DB-->>Tool: tool result
    Tool-->>Agent: JSON result
    Agent->>LLM: function_call_output
    LLM-->>Agent: final answer
    Agent-->>API: answer
    API->>Redis: 保存 session state
    API-->>Frontend: answer + trace_id + pending_approval
    Frontend-->>User: 展示回复
```

---

## Human-in-the-loop Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API
    participant Agent
    participant LLM
    participant Redis
    participant DB as Postgres

    User->>Frontend: 我要取消 A1002，原因是拍错了
    Frontend->>API: POST /chat
    API->>Agent: send(message)
    Agent->>LLM: messages + tools
    LLM-->>Agent: function_call cancel_order
    Agent->>Agent: 检查 TOOL_POLICIES
    Agent->>Agent: cancel_order requires_approval=true
    Agent->>Redis: 保存 pending_approval
    API-->>Frontend: pending_approval
    Frontend-->>User: 显示确认按钮

    User->>Frontend: 点击确认执行
    Frontend->>API: POST /sessions/{id}/approval { decision: approve }
    API->>Redis: 加载 pending_approval
    API->>Agent: submit_approval(approve)
    Agent->>DB: 执行 cancel_order
    DB-->>Agent: 订单已取消
    Agent->>LLM: function_call_output
    LLM-->>Agent: final answer
    Agent->>Redis: 清除 pending_approval，保存 memory
    API-->>Frontend: answer
```

---

## RAG Flow

```mermaid
flowchart TD
    DOCS[docs/*.txt] --> CHUNK[Structured Chunking]
    CHUNK --> META[Add Metadata: source, section, heading_path]
    META --> EMBED[OpenAI Embeddings]
    EMBED --> PGVECTOR[(Postgres document_chunks + pgvector)]

    Q[User Question] --> QEMBED[Query Embedding]
    QEMBED --> SEARCH[Cosine Similarity Search]
    PGVECTOR --> SEARCH
    SEARCH --> TOPK[Top-k Chunks]
    TOPK --> AGENT[Agent Context]
    AGENT --> ANSWER[Answer with Source Citation]
```

---

## Project Structure

```text
support-agent/
├── support_agent/
│   ├── main.py
│   ├── api/
│   │   ├── deps.py
│   │   └── routes/
│   │       ├── auth.py
│   │       ├── chat.py
│   │       ├── sessions.py
│   │       └── health.py
│   ├── agent/
│   │   ├── session.py
│   │   ├── tools.py
│   │   ├── prompts.py
│   │   └── schemas.py
│   ├── rag/
│   │   ├── chunking.py
│   │   ├── retriever.py
│   │   └── indexer.py
│   ├── db/
│   │   ├── session.py
│   │   ├── models.py
│   │   ├── init_db.py
│   │   └── repositories/
│   │       └── orders.py
│   └── core/
│       ├── config.py
│       ├── auth.py
│       ├── rate_limit.py
│       ├── session_store.py
│       └── observability.py
├── scripts/
├── static/
├── docs/
├── tests/
├── Dockerfile
├── docker-compose.yml
└── README.md
```

### Layer Responsibilities

| Module | Responsibility |
|---|---|
| `api` | HTTP routes, request/response models, dependencies |
| `agent` | Agent loop, memory, tool calling, approval |
| `rag` | chunking, embeddings, pgvector retrieval |
| `db` | SQLAlchemy models and repositories |
| `core` | auth, config, Redis session, rate limiting, tracing |
| `static` | frontend demo |
| `tests` | pytest test suite |

---

## Quick Start

### 1. Clone

```bash
git clone <your-repo-url>
cd support-agent
```

### 2. Create `.env`

```bash
cp .env.example .env
```

Edit `.env`:

```env
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-5
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536

REDIS_URL=redis://redis:6379/0
SESSION_TTL_SECONDS=604800

DATABASE_URL=postgresql+psycopg://support_user:support_password@postgres:5432/support_agent

JWT_SECRET_KEY=change-this-to-a-long-random-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

CHAT_RATE_LIMIT_PER_MINUTE=20
CHAT_RATE_LIMIT_PER_DAY=500
LOGIN_IP_RATE_LIMIT_PER_MINUTE=20
LOGIN_USER_IP_RATE_LIMIT_PER_MINUTE=5
```

### 3. Start Services

```bash
docker compose up --build
```

### 4. Initialize Database

```bash
docker compose run --rm support-agent-api python -m scripts.init_db
```

### 5. Build RAG Index

```bash
docker compose run --rm support-agent-api python -m scripts.build_pgvector_index
```

### 6. Open Frontend Demo

```text
http://127.0.0.1:8000/
```

Demo accounts:

```text
alice / alice123
bob / bob123
admin / admin123
```

---

## Local Development

Start Redis and Postgres:

```bash
docker compose up -d redis postgres
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Initialize data:

```bash
python -m scripts.init_db
python -m scripts.build_pgvector_index
```

Run API:

```bash
uvicorn support_agent.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

API docs:

```text
http://127.0.0.1:8000/docs
```

---

## API Examples

### Login

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=alice&password=alice123"
```

Save token:

```bash
TOKEN="your_access_token"
```

### Chat

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我查一下 A1002"
  }'
```

### Continue Session

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "SESSION_ID",
    "message": "那它应该退款还是取消？"
  }'
```

### Approve Pending Action

```bash
curl -X POST http://127.0.0.1:8000/sessions/SESSION_ID/approval \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "approve"
  }'
```

### Reject Pending Action

```bash
curl -X POST http://127.0.0.1:8000/sessions/SESSION_ID/approval \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "reject"
  }'
```

### View Memory

```bash
curl http://127.0.0.1:8000/sessions/SESSION_ID/memory \
  -H "Authorization: Bearer $TOKEN"
```

---

## Tracing

Every `/chat` and `/approval` response includes:

```json
{
  "trace_id": "trace_xxx"
}
```

View trace:

```bash
python scripts/view_trace.py trace_xxx
```

Trace records include:

- HTTP request span
- Agent loop span
- LLM call span
- tool call requested event
- tool execution span
- RAG retrieval result
- pending approval event
- final answer event

Example trace shape:

```text
- http.post./chat
  - agent.send
    - agent.loop
      - llm.responses.create
      * tool.call_requested get_order_status
      - tool.execute.get_order_status
      - llm.responses.create
      * agent.final_answer
```

---

## Testing

Run tests:

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=. --cov-report=term-missing
```

Test coverage includes:

- JWT login
- `/chat` auth
- Redis session
- Approval API
- Postgres permission control
- Rate limiting
- RAG chunking
- pgvector retrieval
- API contract

CI tests mock LLM calls and validate backend reliability.

Agent behavior quality is evaluated separately with `eval_agent.py`.

---

## Security Design

### 1. JWT Authentication

`/chat` does not accept `user_id` in request body.

Instead:

```text
Authorization: Bearer <token>
```

The backend extracts current user identity from JWT.

### 2. Permission Control

Order tools filter by:

```text
current_user.user_id + order_id
```

This prevents users from accessing other users' orders.

### 3. Human-in-the-loop

High-risk tools:

```text
cancel_order
create_refund_ticket
```

are not executed immediately.

They create:

```text
pending_approval
```

The frontend must call:

```http
POST /sessions/{session_id}/approval
```

with:

```json
{
  "decision": "approve"
}
```

before execution.

### 4. Rate Limiting

Redis-based rate limiting protects:

```text
/auth/login
/chat
```

from abuse and LLM cost spikes.

---

## Production Notes

This is a demo project. For production, consider:

- Use Alembic for database migrations
- Store secrets in Secret Manager or Kubernetes Secret
- Use HTTPS
- Configure strict CORS
- Use refresh tokens and token revocation
- Add audit logs for approval actions
- Add tenant / organization isolation
- Add document-level access control for RAG
- Add OpenTelemetry tracing
- Add background jobs for document indexing
- Add streaming response support
- Add model fallback and retry policy
- Add token usage accounting and cost monitoring

---

## Interview Highlights

This project demonstrates:

1. How to implement a hand-written Agent loop with tool calling
2. How to separate model decisions from backend execution
3. How to protect high-risk actions with human-in-the-loop
4. How to design Redis-backed Agent memory
5. How to build RAG with structured chunking and pgvector
6. How to enforce backend authorization instead of trusting prompts
7. How to add tracing for Agent debugging
8. How to test an LLM application without calling the real LLM in CI
9. How to deploy an AI backend with Docker Compose
10. How to structure an AI Agent project like a real backend system