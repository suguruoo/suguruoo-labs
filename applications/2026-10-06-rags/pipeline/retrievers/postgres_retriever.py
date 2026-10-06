# pipeline/retrievers/postgres_retriever.py
"""PostgreSQL (pgvector) Retriever。

ローカル embedding（multilingual-e5-large）を使ったコサイン類似度検索。
OpenAI API は使用しない。
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
from pgvector.psycopg2 import register_vector

from data.embedder import LocalEmbedder
from pipeline.models import PipelineParams, RetrievedDoc, SourceType, StepType
from pipeline.step_logger import StepLogger

logger = logging.getLogger(__name__)


class PostgresRetriever:
    """pgvector cosine similarity + メタデータフィルタによる検索。

    Attributes:
        source: SourceType.POSTGRES。
        _settings: DB接続設定。
        _embedder: ローカル embedding モデル。
    """

    source = SourceType.POSTGRES

    def __init__(self, settings: dict[str, Any], openai_api_key: str = "") -> None:
        """初期化。

        Args:
            settings: PostgreSQL 接続設定。
            openai_api_key: 未使用（互換性のため残す）。
        """
        self._settings = settings
        self._embedder = LocalEmbedder()

    def _embed_query(self, text: str) -> list[float]:
        """クエリテキストを embedding に変換する（ローカル）。

        Args:
            text: 検索クエリテキスト。

        Returns:
            embedding ベクター。
        """
        return self._embedder.embed_query(text)

    def _get_connection(self) -> psycopg2.extensions.connection:
        conn = psycopg2.connect(
            host=self._settings["host"],
            port=self._settings["port"],
            user=self._settings["user"],
            password=self._settings["password"],
            dbname=self._settings["dbname"],
        )
        register_vector(conn)
        return conn

    async def retrieve(
        self,
        query_dict: dict[str, str],
        params: PipelineParams,
        step_logger: StepLogger,
        attempt: int = 1,
    ) -> list[RetrievedDoc]:
        """クエリ辞書を使って PostgreSQL から文書を検索する。

        Args:
            query_dict: QueryAnalyzer が生成したクエリ辞書。
            params: パイプラインパラメータ。
            step_logger: ステップロガー。
            attempt: 試行回数。

        Returns:
            検索結果の RetrievedDoc リスト。
        """
        keywords = query_dict.get("keywords", params.question)
        lang_filter = query_dict.get("lang_filter", params.language)

        embedding = self._embed_query(keywords)

        lang_condition = ""
        if lang_filter in ("ja", "en"):
            lang_condition = f"AND lang = '{lang_filter}'"

        sql = f"""
            SELECT
                url, title, section, lang, content,
                1 - (embedding <=> %s::vector) AS score
            FROM documents
            WHERE 1=1 {lang_condition}
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """

        step_logger.emit_step(
            step=StepType.RETRIEVE_REQUEST,
            data={
                "query": keywords,
                "lang_filter": lang_filter,
                "sql_preview": sql.strip()[:200],
                "top_k": params.top_k,
            },
            attempt=attempt,
        )

        conn = self._get_connection()
        docs: list[RetrievedDoc] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (embedding, embedding, params.top_k * 2))
                rows = cur.fetchall()
                for rank, row in enumerate(rows[: params.top_k]):
                    docs.append(
                        RetrievedDoc(
                            content=row[4],
                            url=row[0],
                            title=row[1] or "",
                            section=row[2] or "",
                            lang=row[3] or "",
                            score=float(row[5]),
                            rank=rank + 1,
                        )
                    )
        finally:
            conn.close()

        step_logger.emit_step(
            step=StepType.RETRIEVE_RESULT,
            data={
                "count": len(docs),
                "docs": [
                    {"rank": d.rank, "score": d.score, "title": d.title, "url": d.url}
                    for d in docs
                ],
            },
            attempt=attempt,
        )
        logger.info("[postgres] retrieve attempt=%d → %d docs", attempt, len(docs))
        return docs
