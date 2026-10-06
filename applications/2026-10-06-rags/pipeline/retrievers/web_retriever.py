# pipeline/retrievers/web_retriever.py
"""Web Retriever。

OpenAI の web_search ツールを使ったリアルタイム検索。
"""

from __future__ import annotations

import logging

from openai import OpenAI

from pipeline.models import PipelineParams, RetrievedDoc, SourceType, StepType
from pipeline.step_logger import StepLogger

logger = logging.getLogger(__name__)


class WebRetriever:
    """OpenAI web_search を使ったリアルタイム Web 検索。

    Attributes:
        source: SourceType.WEB。
        _openai_client: OpenAI クライアント。
    """

    source = SourceType.WEB

    def __init__(self, openai_api_key: str) -> None:
        """初期化。

        Args:
            openai_api_key: OpenAI APIキー。
        """
        self._openai_client = OpenAI(api_key=openai_api_key)

    async def retrieve(
        self,
        query_dict: dict[str, str],
        params: PipelineParams,
        step_logger: StepLogger,
        attempt: int = 1,
    ) -> list[RetrievedDoc]:
        """クエリ辞書を使って Web 検索を実行する。

        Args:
            query_dict: QueryAnalyzer が生成したクエリ辞書。
            params: パイプラインパラメータ。
            step_logger: ステップロガー。
            attempt: 試行回数。

        Returns:
            検索結果の RetrievedDoc リスト。
        """
        query_ja = query_dict.get("query_ja", params.question)
        query_en = query_dict.get("query_en", "")

        # 言語設定に応じてクエリを選択
        if params.language == "en":
            search_query = query_en or query_ja
        elif params.language == "ja":
            search_query = query_ja
        else:
            search_query = f"{query_ja} {query_en}".strip()

        step_logger.emit_step(
            step=StepType.RETRIEVE_REQUEST,
            data={
                "query_ja": query_ja,
                "query_en": query_en,
                "search_query": search_query,
                "top_k": params.top_k,
            },
            attempt=attempt,
        )

        docs: list[RetrievedDoc] = []
        try:
            response = self._openai_client.responses.create(
                model=params.model,
                tools=[{"type": "web_search_preview"}],
                input=search_query,
            )

            for idx, item in enumerate(response.output):
                if hasattr(item, "content"):
                    for content_block in item.content:
                        if hasattr(content_block, "text"):
                            text = content_block.text
                            if text and len(text.strip()) > 50:
                                docs.append(
                                    RetrievedDoc(
                                        content=text,
                                        url="",
                                        title=f"Web Result {idx + 1}",
                                        section="web_search",
                                        lang=params.language if params.language != "ja+en" else "en",
                                        score=1.0 - (idx * 0.05),
                                        rank=len(docs) + 1,
                                    )
                                )
                            if len(docs) >= params.top_k:
                                break
                if len(docs) >= params.top_k:
                    break

        except Exception as exc:
            logger.error("[web] retrieve error: %s", exc)
            step_logger.emit_step(
                step=StepType.ERROR,
                data={"error": str(exc)},
                attempt=attempt,
            )

        step_logger.emit_step(
            step=StepType.RETRIEVE_RESULT,
            data={
                "count": len(docs),
                "docs": [
                    {"rank": d.rank, "score": d.score, "title": d.title, "content_preview": d.content[:100]}
                    for d in docs
                ],
            },
            attempt=attempt,
        )
        logger.info("[web] retrieve attempt=%d → %d docs", attempt, len(docs))
        return docs
