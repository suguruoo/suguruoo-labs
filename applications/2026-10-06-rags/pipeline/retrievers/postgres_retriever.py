# pipeline/retrievers/postgres_retriever.py
"""PostgreSQL (pgvector) Retriever。

ローカル embedding（multilingual-e5-large）+ tsvector によるハイブリッド検索。
Reciprocal Rank Fusion (RRF) で embedding スコアとキーワードスコアを統合する。
OpenAI API は使用しない。

方策①: lang_filter はユーザー設定(params.language)を直接使用（LLM 判断させない）
方策②: 候補数を top_k × 4 に拡大してから最終 top_k に絞る
方策③: tsvector 全文検索スコアと embedding スコアを RRF で統合
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

# RRF 定数（標準値 60）
_RRF_K = 60
# 方策②: 候補プール倍率
_CANDIDATE_MULTIPLIER = 4


class PostgresRetriever:
    """pgvector + tsvector RRF ハイブリッド検索。

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
        """クエリテキストを embedding に変換する（ローカル）。"""
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
        """ハイブリッド検索（embedding RRF + tsvector）で文書を取得する。

        Args:
            query_dict: QueryAnalyzer が生成したクエリ辞書。
            params: パイプラインパラメータ。
            step_logger: ステップロガー。
            attempt: 試行回数。

        Returns:
            検索結果の RetrievedDoc リスト。
        """
        keywords = query_dict.get("keywords", params.question)

        # ── 方策①: lang_filter は params.language を直接使用（LLM 判断を無視）──
        lang_filter = params.language
        candidate_size = params.top_k * _CANDIDATE_MULTIPLIER  # 方策②

        embedding = self._embed_query(keywords)

        lang_condition = ""
        if lang_filter in ("ja", "en"):
            lang_condition = f"AND lang = '{lang_filter}'"

        # tsvector 用: ASCII英数字のみ抽出（日本語カタカナ/漢字を除外してヒット率向上）
        # 例: "DynamoDB クォーター GSI 制限" → "DynamoDB GSI"
        ascii_keywords = " ".join(
            w for w in keywords.split()
            if all(ord(c) < 128 for c in w) and len(w) > 1
        )
        # 英語キーワードが空の場合はフル keywords をそのまま使用
        tsvector_query = ascii_keywords if ascii_keywords.strip() else keywords

        # ── 方策③: RRF ハイブリッド SQL（URL 単位 dedup 付き）──
        # embedding ランク + tsvector ランクを RRF で統合
        # 同一 URL の複数チャンクが embedding を重複加算しないよう
        # emb_ranked では URL ごとに最高スコア（最小距離）のチャンクのみ採用
        sql = f"""
            WITH
            emb_best AS (
                SELECT DISTINCT ON (url) id, url,
                    embedding <=> %s::vector AS dist
                FROM documents
                WHERE 1=1 {lang_condition}
                ORDER BY url, embedding <=> %s::vector
            ),
            emb_ranked AS (
                SELECT id,
                    ROW_NUMBER() OVER (ORDER BY dist) AS rank_emb
                FROM emb_best
                LIMIT %s
            ),
            kw_ranked AS (
                SELECT id,
                    ROW_NUMBER() OVER (
                        ORDER BY ts_rank_cd(
                            to_tsvector('simple',
                                coalesce(title,'') || ' ' || coalesce(content,'')),
                            plainto_tsquery('simple', %s)
                        ) DESC
                    ) AS rank_kw
                FROM documents
                WHERE 1=1 {lang_condition}
                  AND to_tsvector('simple',
                        coalesce(title,'') || ' ' || coalesce(content,''))
                      @@ plainto_tsquery('simple', %s)
                LIMIT %s
            )
            SELECT
                d.url, d.title, d.section, d.lang, d.content,
                (
                    COALESCE(1.0 / ({_RRF_K} + e.rank_emb), 0) +
                    COALESCE(1.0 / ({_RRF_K} + k.rank_kw), 0)
                ) AS rrf_score,
                1 - (d.embedding <=> %s::vector) AS emb_score
            FROM documents d
            LEFT JOIN emb_ranked e ON d.id = e.id
            LEFT JOIN kw_ranked  k ON d.id = k.id
            WHERE e.id IS NOT NULL OR k.id IS NOT NULL
            ORDER BY rrf_score DESC
            LIMIT %s;
        """

        step_logger.emit_step(
            step=StepType.RETRIEVE_REQUEST,
            data={
                "query": keywords,
                "tsvector_query": tsvector_query,
                "lang_filter": lang_filter,
                "method": "hybrid_rrf (embedding + tsvector)",
                "candidate_size": candidate_size,
                "top_k": params.top_k,
            },
            attempt=attempt,
        )

        conn = self._get_connection()
        docs: list[RetrievedDoc] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    embedding,       # emb_best: 距離計算 (DISTINCT ON)
                    embedding,       # emb_best: ORDER BY 距離（dedup用）
                    candidate_size,  # emb_ranked: LIMIT（方策②）
                    tsvector_query,  # kw_ranked: plainto_tsquery WHERE
                    tsvector_query,  # kw_ranked: plainto_tsquery WHERE
                    candidate_size,  # kw_ranked: LIMIT（方策②）
                    embedding,       # emb_score 計算用
                    params.top_k,    # 最終 LIMIT
                ))
                rows = cur.fetchall()
                for rank, row in enumerate(rows):
                    docs.append(
                        RetrievedDoc(
                            content=row[4],
                            url=row[0],
                            title=row[1] or "",
                            section=row[2] or "",
                            lang=row[3] or "",
                            score=float(row[5]),  # rrf_score
                            rank=rank + 1,
                        )
                    )

            # tsvector でヒットがゼロの場合: embedding only fallback
            if not docs:
                logger.info("[postgres] RRF 0 hits → fallback to embedding-only")
                fb_sql = f"""
                    SELECT url, title, section, lang, content,
                           1 - (embedding <=> %s::vector) AS score
                    FROM documents
                    WHERE 1=1 {lang_condition}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                """
                with conn.cursor() as cur:
                    cur.execute(fb_sql, (embedding, embedding, params.top_k))
                    for rank, row in enumerate(cur.fetchall()):
                        docs.append(
                            RetrievedDoc(
                                content=row[4], url=row[0], title=row[1] or "",
                                section=row[2] or "", lang=row[3] or "",
                                score=float(row[5]), rank=rank + 1,
                            )
                        )
        finally:
            conn.close()

        step_logger.emit_step(
            step=StepType.RETRIEVE_RESULT,
            data={
                "count": len(docs),
                "method": "hybrid_rrf",
                "docs": [
                    {"rank": d.rank, "score": round(d.score, 4),
                     "title": d.title, "url": d.url}
                    for d in docs
                ],
            },
            attempt=attempt,
        )
        logger.info("[postgres] hybrid retrieve attempt=%d → %d docs", attempt, len(docs))
        return docs
