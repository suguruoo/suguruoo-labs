# data/mysql_loader.py
"""MySQL へのデータロード。

ページメタ情報 + 本文を FULLTEXT INDEX 付きのテーブルに格納する。
"""

from __future__ import annotations

import logging
from typing import Any

import pymysql
import pymysql.cursors

from data.chunker import Chunk

logger = logging.getLogger(__name__)

_BATCH_SIZE = 200


def _get_connection(settings: dict[str, Any]) -> pymysql.connections.Connection:
    """MySQL 接続を返す。"""
    return pymysql.connect(
        host=settings["host"],
        port=settings["port"],
        user=settings["user"],
        password=settings["password"],
        database=settings["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def init_schema(settings: dict[str, Any]) -> None:
    """テーブルとインデックスを初期化する。

    Args:
        settings: 接続設定辞書。
    """
    conn = _get_connection(settings)
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INT AUTO_INCREMENT PRIMARY KEY,
                url VARCHAR(2048) NOT NULL,
                lang VARCHAR(5) NOT NULL,
                source_type VARCHAR(50) NOT NULL,
                title TEXT,
                section TEXT,
                chunk_index INT NOT NULL,
                content MEDIUMTEXT NOT NULL,
                keywords TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_lang (lang),
                INDEX idx_source_type (source_type),
                FULLTEXT INDEX ft_content (title, section, content, keywords)
                    WITH PARSER ngram
            ) ENGINE=InnoDB
              DEFAULT CHARSET=utf8mb4
              COLLATE=utf8mb4_unicode_ci;
        """)
    conn.commit()
    conn.close()
    logger.info("mysql schema initialized")


def load_chunks(chunks: list[Chunk], settings: dict[str, Any]) -> None:
    """チャンクを MySQL に格納する。

    Args:
        chunks: チャンクリスト。
        settings: DB接続設定。
    """
    conn = _get_connection(settings)

    try:
        for batch_start in range(0, len(chunks), _BATCH_SIZE):
            batch = chunks[batch_start: batch_start + _BATCH_SIZE]
            with conn.cursor() as cur:
                for chunk in batch:
                    cur.execute(
                        """
                        INSERT INTO documents
                            (url, lang, source_type, title, section,
                             chunk_index, content, keywords)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            chunk.url,
                            chunk.lang,
                            chunk.source_type,
                            chunk.title,
                            chunk.section,
                            chunk.chunk_index,
                            chunk.content,
                            ", ".join(chunk.keywords) if chunk.keywords else "",
                        ),
                    )
            conn.commit()
            logger.info(
                "mysql: inserted batch %d-%d / %d",
                batch_start,
                batch_start + len(batch),
                len(chunks),
            )
    finally:
        conn.close()

    logger.info("mysql: load_chunks done (%d chunks)", len(chunks))
