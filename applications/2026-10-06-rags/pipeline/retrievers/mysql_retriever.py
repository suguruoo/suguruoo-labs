# pipeline/retrievers/mysql_retriever.py
"""MySQL FULLTEXT Retriever。

MATCH() AGAINST() BOOLEAN MODE による BM25相当のキーワード検索。
"""

from __future__ import annotations

import logging
from typing import Any

import pymysql
import pymysql.cursors

from pipeline.models import PipelineParams, RetrievedDoc, SourceType, StepType
from pipeline.step_logger import StepLogger

logger = logging.getLogger(__name__)


class MySQLRetriever:
    """MySQL FULLTEXT BOOLEAN MODE 検索。

    Attributes:
        source: SourceType.MYSQL。
        _settings: DB接続設定。
    """

    source = SourceType.MYSQL

    def __init__(self, settings: dict[str, Any]) -> None:
        """初期化。

        Args:
            settings: MySQL 接続設定。
        """
        self._settings = settings

    def _get_connection(self) -> pymysql.connections.Connection:
        return pymysql.connect(
            host=self._settings["host"],
            port=self._settings["port"],
            user=self._settings["user"],
            password=self._settings["password"],
            database=self._settings["database"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )

    async def retrieve(
        self,
        query_dict: dict[str, str],
        params: PipelineParams,
        step_logger: StepLogger,
        attempt: int = 1,
    ) -> list[RetrievedDoc]:
        """クエリ辞書を使って MySQL から文書を検索する。

        Args:
            query_dict: QueryAnalyzer が生成したクエリ辞書。
            params: パイプラインパラメータ。
            step_logger: ステップロガー。
            attempt: 試行回数。

        Returns:
            検索結果の RetrievedDoc リスト。
        """
        boolean_query = query_dict.get("boolean_query", "")
        keywords_plain = query_dict.get("keywords_plain", params.question)

        if not boolean_query:
            words = keywords_plain.split()
            boolean_query = " ".join(f"+{w}" for w in words if len(w) > 1)

        lang_condition = ""
        if params.language in ("ja", "en"):
            lang_condition = f"AND lang = '{params.language}'"

        sql = f"""
            SELECT
                url, title, section, lang, content,
                MATCH(title, section, content, keywords)
                    AGAINST (%s IN BOOLEAN MODE) AS score
            FROM documents
            WHERE MATCH(title, section, content, keywords)
                  AGAINST (%s IN BOOLEAN MODE) > 0
            {lang_condition}
            ORDER BY score DESC
            LIMIT %s;
        """

        step_logger.emit_step(
            step=StepType.RETRIEVE_REQUEST,
            data={
                "boolean_query": boolean_query,
                "lang_filter": params.language,
                "sql_preview": sql.strip()[:200],
                "top_k": params.top_k,
            },
            attempt=attempt,
        )

        conn = self._get_connection()
        docs: list[RetrievedDoc] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (boolean_query, boolean_query, params.top_k * 2))
                rows = cur.fetchall()
                for rank, row in enumerate(rows[: params.top_k]):
                    docs.append(
                        RetrievedDoc(
                            content=row["content"],
                            url=row["url"],
                            title=row["title"] or "",
                            section=row["section"] or "",
                            lang=row["lang"] or "",
                            score=float(row["score"]),
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
        logger.info("[mysql] retrieve attempt=%d → %d docs", attempt, len(docs))
        return docs
