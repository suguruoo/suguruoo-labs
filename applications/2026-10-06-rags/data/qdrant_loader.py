# data/qdrant_loader.py
"""Qdrant へのデータロード。

ローカル embedding（multilingual-e5-large）のみを Qdrant collection に格納する。
OpenAI API は使用しない。
"""

from __future__ import annotations

import logging

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from data.chunker import Chunk
from data.embedder import EMBEDDING_DIM, LocalEmbedder

logger = logging.getLogger(__name__)

_BATCH_SIZE = 64


def init_collection(host: str, port: int, collection_name: str) -> None:
    """Qdrant コレクションを初期化する。既存の場合はスキップ。

    Args:
        host: Qdrant ホスト。
        port: Qdrant ポート。
        collection_name: コレクション名。
    """
    client = QdrantClient(host=host, port=port)
    existing = [c.name for c in client.get_collections().collections]
    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        logger.info("qdrant: collection '%s' created (dim=%d)", collection_name, EMBEDDING_DIM)
    else:
        logger.info("qdrant: collection '%s' already exists", collection_name)


def load_chunks(
    chunks: list[Chunk],
    host: str,
    port: int,
    collection_name: str,
    id_offset: int = 0,
) -> None:
    """チャンクをローカル embedding 化して Qdrant に格納する。

    OpenAI API は使用しない。sentence-transformers でローカル生成。

    Args:
        chunks: チャンクリスト。
        host: Qdrant ホスト。
        port: Qdrant ポート。
        collection_name: コレクション名。
        id_offset: Point ID の開始オフセット。
    """
    qdrant_client = QdrantClient(host=host, port=port)
    embedder = LocalEmbedder()

    for batch_start in range(0, len(chunks), _BATCH_SIZE):
        batch = chunks[batch_start: batch_start + _BATCH_SIZE]
        texts = [c.content for c in batch]
        embeddings = embedder.embed_passages(texts)

        points = [
            PointStruct(
                id=id_offset + batch_start + idx,
                vector=embedding,
                payload={
                    "url": chunk.url,
                    "lang": chunk.lang,
                    "source_type": chunk.source_type,
                    "title": chunk.title,
                    "section": chunk.section,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "keywords": chunk.keywords,
                },
            )
            for idx, (chunk, embedding) in enumerate(zip(batch, embeddings))
        ]

        qdrant_client.upsert(collection_name=collection_name, points=points)
        logger.info(
            "qdrant: upserted batch %d-%d / %d",
            batch_start,
            batch_start + len(batch),
            len(chunks),
        )

    logger.info("qdrant: load_chunks done (%d chunks)", len(chunks))

