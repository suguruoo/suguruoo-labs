# data/postgres_loader.py
"""PostgreSQL (pgvector) へのデータロード。

chunks + ローカル embedding（multilingual-e5-large）を documents テーブルに格納する。
OpenAI API は使用しない。
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
from pgvector.psycopg2 import register_vector

from data.chunker import Chunk
from data.embedder import EMBEDDING_DIM, LocalEmbedder

logger = logging.getLogger(__name__)

_BATCH_SIZE = 64  # sentence-transformers はバッチ推論が効率的


def _get_connection(settings: dict[str, Any]) -> psycopg2.extensions.connection:
    """PostgreSQL 接続を返す。"""
    return psycopg2.connect(
        host=settings["host"],
        port=settings["port"],
        user=settings["user"],
        password=settings["password"],
        dbname=settings["dbname"],
    )


def init_schema(settings: dict[str, Any]) -> None:
    """テーブルとインデックスを初期化する。

    Args:
        settings: 接続設定辞書。
    """
    conn = _get_connection(settings)
    # まず extension を作成してコミットしてから register_vector を呼ぶ
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    conn.commit()

    register_vector(conn)
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                url TEXT NOT NULL,
                lang VARCHAR(5) NOT NULL,
                source_type VARCHAR(50) NOT NULL,
                title TEXT,
                section TEXT,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                keywords TEXT[],
                embedding vector(%s),
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """, (EMBEDDING_DIM,))
        cur.execute("""
            CREATE INDEX IF NOT EXISTS documents_embedding_idx
            ON documents USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS documents_lang_idx ON documents (lang);")
        cur.execute("CREATE INDEX IF NOT EXISTS documents_source_type_idx ON documents (source_type);")
    conn.commit()
    conn.close()
    logger.info("postgres schema initialized (embedding_dim=%d)", EMBEDDING_DIM)


def load_chunks(chunks: list[Chunk], settings: dict[str, Any]) -> None:
    """チャンクをローカル embedding 化して PostgreSQL に格納する。

    OpenAI API は使用しない。sentence-transformers でローカル生成。

    Args:
        chunks: チャンクリスト。
        settings: DB接続設定。
    """
    conn = _get_connection(settings)
    register_vector(conn)
    embedder = LocalEmbedder()

    try:
        for batch_start in range(0, len(chunks), _BATCH_SIZE):
            batch = chunks[batch_start: batch_start + _BATCH_SIZE]
            texts = [c.content for c in batch]
            embeddings = embedder.embed_passages(texts)

            with conn.cursor() as cur:
                for chunk, embedding in zip(batch, embeddings):
                    cur.execute(
                        """
                        INSERT INTO documents
                            (url, lang, source_type, title, section,
                             chunk_index, content, keywords, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING;
                        """,
                        (
                            chunk.url,
                            chunk.lang,
                            chunk.source_type,
                            chunk.title,
                            chunk.section,
                            chunk.chunk_index,
                            chunk.content,
                            chunk.keywords,
                            embedding,
                        ),
                    )
            conn.commit()
            logger.info(
                "postgres: inserted batch %d-%d / %d",
                batch_start,
                batch_start + len(batch),
                len(chunks),
            )
    finally:
        conn.close()

    logger.info("postgres: load_chunks done (%d chunks)", len(chunks))



def _get_connection(settings: dict[str, Any]) -> psycopg2.extensions.connection:
    """PostgreSQL 接続を返す。"""
    return psycopg2.connect(
        host=settings["host"],
        port=settings["port"],
        user=settings["user"],
        password=settings["password"],
        dbname=settings["dbname"],
    )


