import json
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import select

from mini_agent.core.config import get_settings

from mini_agent.db.session import db_session

from mini_agent.db.models import DocumentChunk

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")


def get_embedding(text: str) -> List[float]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )

    return response.data[0].embedding


def search_policy_chunks(
    query: str,
    *,
    top_k: int = 3,
    score_threshold: float = 0.25,
) -> List[Dict[str, Any]]:
    """
    使用 pgvector 做 cosine distance 检索。

    pgvector 的 cosine_distance 越小越相似。
    为了和旧版本保持一致，我们转换成 similarity：

        similarity = 1 - cosine_distance
    """
    query_embedding = get_embedding(query)

    with db_session() as db:
        distance_expr = DocumentChunk.embedding.cosine_distance(
            query_embedding
        )

        stmt = (
            select(
                DocumentChunk,
                distance_expr.label("distance"),
            )
            .order_by(distance_expr)
            .limit(top_k)
        )

        rows = db.execute(stmt).all()

    results: List[Dict[str, Any]] = []

    for chunk, distance in rows:
        distance_float = float(distance)
        similarity = 1.0 - distance_float

        if similarity < score_threshold:
            continue

        try:
            heading_path = json.loads(chunk.heading_path)
        except Exception:
            heading_path = []

        citation = (
            f"{chunk.source} / {chunk.section}"
            if chunk.section
            else chunk.source
        )

        results.append({
            "id": chunk.id,
            "source": chunk.source,
            "section": chunk.section,
            "citation": citation,
            "heading_path": heading_path,
            "chunk_index": chunk.chunk_index,
            "score": round(similarity, 4),
            "distance": round(distance_float, 4),
            "text": chunk.text,
        })

    return results


def search_policy_knowledge_base(query: str) -> Dict[str, Any]:
    try:
        chunks = search_policy_chunks(
            query=query,
            top_k=3,
            score_threshold=0.25,
        )

        return {
            "success": True,
            "query": query,
            "found": len(chunks) > 0,
            "top_k": 3,
            "score_threshold": 0.25,
            "backend": "postgres_pgvector",
            "results": chunks,
        }

    except Exception as e:
        return {
            "success": False,
            "query": query,
            "found": False,
            "backend": "postgres_pgvector",
            "error": "rag_search_error",
            "message": str(e),
            "results": [],
        }


if __name__ == "__main__":
    questions = [
        "未发货订单可以退款吗？",
        "质量问题退款需要什么材料？",
        "国际订单多久能到？",
        "黑卡会员有什么权益？",
    ]

    for question in questions:
        print("=" * 80)
        print(f"问题：{question}")
        result = search_policy_knowledge_base(question)
        print(json.dumps(result, ensure_ascii=False, indent=2))