# Project Highlights

## 1. 手写 Agent Loop

没有一开始依赖 LangChain，而是基于 Responses API 手写 Agent loop，理解 tool_call、function_call_output、call_id、tool router 的底层流程。

## 2. Tool Calling + 真实业务工具

Agent 可以调用：

- get_order_status
- cancel_order
- create_refund_ticket
- search_policy_knowledge_base

LLM 只负责提出工具调用，真实执行由后端完成。

## 3. Human-in-the-loop

取消订单和退款工单属于高风险写操作，不会直接执行。系统会创建 pending approval，用户通过独立 Approval API 确认后才执行。

## 4. Redis-backed Memory

AgentSession 状态序列化保存到 Redis，包括：

- last_order_id
- pending_approval
- tool_calls
- input_items

支持服务重启恢复、多 worker 共享 session。

## 5. Postgres 业务数据

订单、用户和退款工单存储到 Postgres，订单权限在数据库层用 user_id 过滤。

## 6. RAG + pgvector

知识库文档按标题和段落切 chunk，embedding 存入 Postgres + pgvector，支持相似度检索和来源引用。

## 7. Security

- JWT Bearer 鉴权
- 不信任前端传 user_id
- 后端权限校验
- 写操作审批
- Rate limiting
- Trace 审计

## 8. Observability

每次请求返回 trace_id，可查看：

- LLM 调用
- tool call
- tool result
- RAG retrieval
- approval decision
- final answer

## 9. Testing

CI 中 mock LLM，重点测试后端工程可靠性，Agent 行为用独立 eval 测试。