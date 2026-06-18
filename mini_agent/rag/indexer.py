import json
import os
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import delete

from mini_agent.db.session import Base, db_session, engine
from mini_agent.db.models import DocumentChunk
from mini_agent.db.init_db import create_extensions
from mini_agent.rag.chunking import build_chunks_for_document

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DOCS_DIR = Path("docs")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")


def read_documents() -> List[Dict[str, str]]:
    documents = []

    for path in DOCS_DIR.glob("*.txt"):
        text = path.read_text(encoding="utf-8")

        documents.append({
            "source": path.name,
            "text": text,
        })

    return documents


def embed_texts(texts: List[str]) -> List[List[float]]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )

    return [item.embedding for item in response.data]


def rebuild_pgvector_index() -> None:
    """
    重建知识库索引。

    Demo 版本：
    - 先删除全部 document_chunks
    - 再重新写入所有 docs/*.txt 的 chunk

    生产版本：
    - 应该按 source / document_id 增量更新
    - 不要每次全删
    """
    create_extensions()
    Base.metadata.create_all(bind=engine)

    docs = read_documents()

    if not docs:
        raise RuntimeError("docs 目录下没有找到 .txt 文档。")

    all_chunks = []

    for doc in docs:
        chunks = build_chunks_for_document(
            source=doc["source"],
            text=doc["text"],
            max_chars=800,
            overlap_paragraphs=1,
        )

        for chunk in chunks:
            all_chunks.append(chunk)

    if not all_chunks:
        raise RuntimeError("没有生成任何 chunk，请检查文档内容。")

    texts = [chunk.text for chunk in all_chunks]
    embeddings = embed_texts(texts)

    with db_session() as db:
        db.execute(delete(DocumentChunk))

        for chunk, embedding in zip(all_chunks, embeddings):
            db.add(
                DocumentChunk(
                    id=chunk.id,
                    source=chunk.source,
                    section=chunk.section,
                    heading_path=json.dumps(
                        chunk.heading_path,
                        ensure_ascii=False,
                    ),
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    embedding=embedding,
                )
            )

    print("pgvector 知识库索引已重建。")
    print(f"文档数：{len(docs)}")
    print(f"chunk 数：{len(all_chunks)}")

    print("\nChunk 预览：")
    for chunk in all_chunks[:5]:
        print("-" * 60)
        print(f"id: {chunk.id}")
        print(f"source: {chunk.source}")
        print(f"section: {chunk.section}")
        print(chunk.text[:300])


if __name__ == "__main__":
    rebuild_pgvector_index()