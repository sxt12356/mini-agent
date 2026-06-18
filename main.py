from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mini_agent.api.routes import auth, chat, health, sessions
from mini_agent.core.session_store import RedisSessionStore, create_redis_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    redis_client = create_redis_client()
    store = RedisSessionStore(redis_client)

    await store.ping()

    app.state.redis_client = redis_client
    app.state.session_store = store

    yield

    await redis_client.aclose()


app = FastAPI(
    title="E-commerce Support Agent API",
    description="电商售后 AI Agent：订单工具 + RAG 知识库 + Memory + Human-in-the-loop",
    version="0.4.0",
    lifespan=lifespan,
)


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(sessions.router)


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")