from sqlalchemy import delete

from mini_agent.db.session import db_session
from mini_agent.db.models import DocumentChunk, EMBEDDING_DIM
from mini_agent.rag.retriever import search_policy_chunks


def chunk_to_kwargs(chunk: DocumentChunk):
    return {
        "id": chunk.id,
        "source": chunk.source,
        "section": chunk.section,
        "heading_path": chunk.heading_path,
        "chunk_index": chunk.chunk_index,
        "text": chunk.text,
        "embedding": list(chunk.embedding),
    }


def zero_vector():
    return [0.0] * EMBEDDING_DIM


def vector_with_first(value: float):
    v = zero_vector()
    v[0] = value
    return v


def test_pgvector_search_returns_best_chunk(monkeypatch):
    def fake_get_embedding(text: str):
        return vector_with_first(1.0)

    monkeypatch.setattr(
        "mini_agent.rag.retriever.get_embedding",
        fake_get_embedding,
    )

    with db_session() as db:
        original_chunks = [
            chunk_to_kwargs(chunk)
            for chunk in db.query(DocumentChunk).all()
        ]

    try:
        with db_session() as db:
            db.execute(delete(DocumentChunk))

            db.add_all([
                DocumentChunk(
                    id="test-refund#0",
                    source="refund_policy.txt",
                    section="退款政策 / 退款条件",
                    heading_path='["退款政策", "退款条件"]',
                    chunk_index=0,
                    text="未发货订单不走退款流程，用户应优先取消订单。",
                    embedding=vector_with_first(1.0),
                ),
                DocumentChunk(
                    id="test-membership#0",
                    source="membership_policy.txt",
                    section="会员政策 / 黑卡会员",
                    heading_path='["会员政策", "黑卡会员"]',
                    chunk_index=0,
                    text="黑卡会员享受免费退货服务。",
                    embedding=vector_with_first(-1.0),
                ),
            ])

        results = search_policy_chunks(
            "未发货订单可以退款吗？",
            top_k=1,
            score_threshold=-1.0,
        )

        assert len(results) == 1
        assert results[0]["source"] == "refund_policy.txt"
        assert results[0]["section"] == "退款政策 / 退款条件"
        assert "未发货订单" in results[0]["text"]

    finally:
        with db_session() as db:
            db.execute(delete(DocumentChunk))
            db.add_all(
                DocumentChunk(**chunk)
                for chunk in original_chunks
            )
