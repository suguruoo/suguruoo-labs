# pipeline/retrievers/qdrant_retriever.py
"""Qdrant Vector DB Retriever。

ローカル embedding（multilingual-e5-large）によるコサイン類似度検索。
OpenAI API は使用しない。
"""

from __future__ import annotations

import logging

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from data.embedder import LocalEmbedder
from pipeline.models import PipelineParams, RetrievedDoc, SourceType, StepType
from pipeline.step_logger import StepLogger

logger = logging.getLogger(__name__)


class QdrantRetriever:
    """Qdrant cosine similarity 検索。

    Attributes:
        source: SourceType.QDRANT。
        _client: QdrantClient インスタンス。
        _embedder: ローカル embedding モデル。
        _collection_name: コレクション名。
    """

    source = SourceType.QDRANT

    def __init__(
        self,
        host: str,
        port: int,
        collection_name: str,
        openai_api_key: str = "",
    ) -> None:
        """初期化。

        Args:
            host: Qdrant ホスト。
            port: Qdrant ポート。
            collection_name: コレクション名。
            openai_api_key: 未使用（互換性のため残す）。
        """
        self._client = QdrantClient(host=host, port=port)
        self._embedder = LocalEmbedder()
        self._collection_name = collection_name

    async def retrieve(
        self,
        query_dict: dict[str, str],
        params: PipelineParams,
        step_logger: StepLogger,
        attempt: int = 1,
    ) -> list[RetrievedDoc]:
        """クエリ辞書を使って Qdrant から文書を検索する。

        Args:
            query_dict: QueryAnalyzer が生成したクエリ辞書。
            params: パイプラインパラメータ。
            step_logger: ステップロガー。
            attempt: 試行回数。

        Returns:
            検索結果の RetrievedDoc リスト。
        """
        query_text = query_dict.get("expanded_query") or query_dict.get("query_text", params.question)

        # ローカルモデルでクエリ embedding を生成（OpenAI API 不要）
        embedding = self._embedder.embed_query(query_text)

        qdrant_filter: Filter | None = None
        if params.language in ("ja", "en"):
            qdrant_filter = Filter(
                must=[FieldCondition(key="lang", match=MatchValue(value=params.language))]
            )

        step_logger.emit_step(
            step=StepType.RETRIEVE_REQUEST,
            data={
                "query_text": query_text,
                "lang_filter": params.language,
                "collection": self._collection_name,
                "top_k": params.top_k,
            },
            attempt=attempt,
        )

        results = self._client.query_points(
            collection_name=self._collection_name,
            query=embedding,
            query_filter=qdrant_filter,
            limit=params.top_k,
            with_payload=True,
        ).points

        docs: list[RetrievedDoc] = []
        for rank, result in enumerate(results):
            payload = result.payload or {}
            docs.append(
                RetrievedDoc(
                    content=payload.get("content", ""),
                    url=payload.get("url", ""),
                    title=payload.get("title", ""),
                    section=payload.get("section", ""),
                    lang=payload.get("lang", ""),
                    score=float(result.score),
                    rank=rank + 1,
                )
            )

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
        logger.info("[qdrant] retrieve attempt=%d → %d docs", attempt, len(docs))
        return docs

