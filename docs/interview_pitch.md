# Interview Pitch

## 30 秒版本

我做了一个电商售后 AI Agent 系统。它可以查询订单、处理取消订单和退款工单，也可以通过 RAG 回答企业政策问题。系统使用 FastAPI 做后端，Redis 保存 Agent 会话状态，Postgres 保存业务数据，pgvector 做知识库向量检索。高风险写操作会进入 human-in-the-loop，用户确认前不会真正执行。

## 1 分钟版本

这个项目是一个完整的 AI Agent 后端系统，不是普通 Chatbot。用户可以问订单状态、退款政策，也可以发起取消订单。Agent 通过 function calling 调用后端工具，订单工具访问 Postgres，政策问答通过 RAG 检索 pgvector 知识库。AgentSession 会把 last_order_id、pending approval、tool calls 保存到 Redis，所以可以支持“取消刚才那个订单”这种多轮指代。

在安全方面，/chat 使用 JWT 鉴权，不接受前端传 user_id。订单权限在数据库层用 current_user.user_id 过滤。取消订单和退款工单属于高风险写操作，模型只能提出 tool call，后端会创建 pending approval，用户通过结构化 approval API 确认后才执行。

## 3 分钟版本

我这个项目主要想解决一个真实业务问题：电商售后客服里，用户既会问订单状态，也会问退款、配送、会员政策，还可能要求取消订单或申请退款。普通 Chatbot 只能回答文本，而我的系统通过 Agent tool calling 接入真实业务工具和知识库。

系统分成几层。API 层用 FastAPI，负责 JWT 登录、/chat、approval 和 memory 接口。Agent 层实现手写 Agent loop，维护 Memory、pending approval、工具调用和系统 prompt。工具层包括订单查询、取消订单、退款工单和政策知识库搜索。业务数据存在 Postgres，Agent session 存 Redis，知识库 chunk 和 embedding 存在 Postgres + pgvector。

RAG 部分我不是简单固定长度切分，而是按标题和段落做结构化 chunking，保留 source、section、heading_path metadata。检索时用户问题先生成 embedding，然后用 pgvector 做 cosine similarity top-k 检索，最后让模型基于检索到的 chunks 回答，并输出来源。

安全方面，我把模型决策和后端执行分开。模型可以提出 cancel_order tool call，但后端根据 TOOL_POLICIES 判断这是 high_write 操作，所以不会立即执行，而是创建 pending approval。前端展示确认按钮，用户调用独立 approval API 后，后端才执行真实工具。权限判断也不靠 prompt，而是在数据库层用 current_user.user_id 做过滤，避免越权访问订单。

为了工程稳定性，我加了 trace_id，记录 LLM 调用、工具调用、RAG 检索和审批状态；加了 Redis rate limiting 控制登录和 /chat 调用频率；还写了 pytest 和 CI，mock LLM 调用，测试 JWT、Redis session、Postgres 权限、Rate Limit、Approval API 和 RAG chunking。