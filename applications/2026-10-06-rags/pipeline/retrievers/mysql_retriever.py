# pipeline/retrievers/mysql_retriever.py
"""MySQL FULLTEXT Retriever。

修正内容:
- 接続後に SET NAMES utf8mb4 で文字コードを明示（latin1 化けを防止）
- ASCII 抽出で英語キーワードを優先（日本語混在クエリの精度劣化を防止）
- URL 単位 dedup で同一ページの複数チャンク重複を防止
- ヒット 0 件時は NATURAL LANGUAGE MODE でリトライ
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
    """MySQL FULLTEXT BOOLEAN MODE + URL dedup 検索。"""

    source = SourceType.MYSQL

    def __init__(self, settings: dict[str, Any]) -> None:
        self._settings = settings

    def _get_connection(self) -> pymysql.connections.Connection:
        """接続後に SET NAMES utf8mb4 を実行して文字コードを確定させる。"""
        conn = pymysql.connect(
            host=self._settings["host"],
            port=self._settings["port"],
            user=self._settings["user"],
            password=self._settings["password"],
            database=self._settings["database"],
            charset="utf8mb4",
            use_unicode=True,
            cursorclass=pymysql.cursors.DictCursor,
        )
        conn.autocommit(True)
        with conn.cursor() as cur:
            cur.execute("SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.execute("SET CHARACTER SET utf8mb4")
        conn.autocommit(False)
        return conn

    @staticmethod
    def _build_boolean_query(query_dict: dict[str, str], question: str) -> tuple[str, str]:
        """BOOLEAN MODE クエリと表示用ラベルを生成する。

        英語 ASCII キーワードを優先する。日本語混在クエリは
        ngram で過分割されてスコアが汚染されるため、
        ASCII 部分だけ抽出して BOOLEAN クエリに使う。

        Returns:
            (boolean_query, display_label) のタプル。
        """
        boolean_query = query_dict.get("boolean_query", "")
        keywords_plain = query_dict.get("keywords_plain", question)

        # ASCII(英数字)トークンのみ抽出
        ascii_words = [
            w.lstrip("+-")
            for w in keywords_plain.split()
            if all(ord(c) < 128 for c in w.lstrip("+-")) and len(w.lstrip("+-")) > 1
        ]

        if ascii_words:
            ascii_boolean = " ".join(f"+{w}" for w in ascii_words)
            return ascii_boolean, f"ascii_boolean: {ascii_boolean}"

        # ASCII が空なら QueryAnalyzer の boolean_query を使用
        if not boolean_query:
            words = keywords_plain.split()
            boolean_query = " ".join(f"+{w}" for w in words if len(w) > 1)

        return boolean_query, f"boolean: {boolean_query}"

    async def retrieve(
        self,
        query_dict: dict[str, str],
        params: PipelineParams,
        step_logger: StepLogger,
        attempt: int = 1,
    ) -> list[RetrievedDoc]:
        """URL dedup 付き FULLTEXT BOOLEAN MODE 検索を実行する。"""
        boolean_query, query_label = self._build_boolean_query(query_dict, params.question)

        lang_condition = ""
        if params.language in ("ja", "en"):
            lang_condition = f"AND lang = '{params.language}'"

        # URL 単位 dedup: 同一 URL の中で最高スコアのチャンクのみ採用
        sql = f"""
            SELECT url, title, section, lang, content, score
            FROM (
                SELECT
                    url, title, section, lang, content,
                    MATCH(title, section, content, keywords)
                        AGAINST (%s IN BOOLEAN MODE) AS score,
                    ROW_NUMBER() OVER (
                        PARTITION BY url
                        ORDER BY MATCH(title, section, content, keywords)
                            AGAINST (%s IN BOOLEAN MODE) DESC
                    ) AS rn
                FROM documents
                WHERE MATCH(title, section, content, keywords)
                      AGAINST (%s IN BOOLEAN MODE) > 0
                {lang_condition}
            ) ranked
            WHERE rn = 1
            ORDER BY score DESC
            LIMIT %s;
        """

        step_logger.emit_step(
            step=StepType.RETRIEVE_REQUEST,
            data={
                "boolean_query": boolean_query,
                "query_label": query_label,
                "lang_filter": params.language,
                "method": "fulltext_boolean_dedup",
                "top_k": params.top_k,
            },
            attempt=attempt,
        )

        conn = self._get_connection()
        docs: list[RetrievedDoc] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (boolean_query, boolean_query, boolean_query, params.top_k))
                for rank, row in enumerate(cur.fetchall()):
                    docs.append(RetrievedDoc(
                        content=row["content"], url=row["url"],
                        title=row["title"] or "", section=row["section"] or "",
                        lang=row["lang"] or "", score=float(row["score"]), rank=rank + 1,
                    ))

            # ヒット 0 件: NATURAL LANGUAGE MODE でリトライ
            if not docs:
                logger.info("[mysql] BOOLEAN 0 hits → fallback NATURAL LANGUAGE MODE")
                or_query = boolean_query.replace("+", "").strip()
                fb_sql = f"""
                    SELECT url, title, section, lang, content,
                        MATCH(title, section, content, keywords)
                            AGAINST (%s IN NATURAL LANGUAGE MODE) AS score
                    FROM documents
                    WHERE MATCH(title, section, content, keywords)
                          AGAINST (%s IN NATURAL LANGUAGE MODE) > 0
                    {lang_condition}
                    ORDER BY score DESC
                    LIMIT %s;
                """
                with conn.cursor() as cur:
                    cur.execute(fb_sql, (or_query, or_query, params.top_k))
                    for rank, row in enumerate(cur.fetchall()):
                        docs.append(RetrievedDoc(
                            content=row["content"], url=row["url"],
                            title=row["title"] or "", section=row["section"] or "",
                            lang=row["lang"] or "", score=float(row["score"]), rank=rank + 1,
                        ))
        finally:
            conn.close()

        step_logger.emit_step(
            step=StepType.RETRIEVE_RESULT,
            data={
                "count": len(docs),
                "method": "fulltext_boolean_dedup",
                "docs": [
                    {"rank": d.rank, "score": round(d.score, 4),
                     "title": d.title, "url": d.url}
                    for d in docs
                ],
            },
            attempt=attempt,
        )
        logger.info("[mysql] retrieve attempt=%d → %d docs", attempt, len(docs))
        return docs

