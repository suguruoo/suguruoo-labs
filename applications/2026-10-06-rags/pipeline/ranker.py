# pipeline/ranker.py
"""独立 Ranker。

取得文書を score でソートして Top-K を選定する。
"""

from __future__ import annotations

import logging

from pipeline.models import PipelineParams, RetrievedDoc, SourceType, StepType
from pipeline.step_logger import StepLogger

logger = logging.getLogger(__name__)


class Ranker:
    """スコアベースで Top-K 文書を選定する。

    Attributes:
        source: ソース種別。
    """

    def __init__(self, source: SourceType) -> None:
        """初期化。

        Args:
            source: ソース種別。
        """
        self.source = source

    def rank(
        self,
        docs: list[RetrievedDoc],
        params: PipelineParams,
        step_logger: StepLogger,
        attempt: int = 1,
    ) -> list[RetrievedDoc]:
        """文書を score 降順でソートして Top-K を返す。

        Args:
            docs: 検索結果文書リスト。
            params: パイプラインパラメータ。
            step_logger: ステップロガー。
            attempt: 試行回数。

        Returns:
            Top-K の RetrievedDoc リスト（rank が振り直されている）。
        """
        sorted_docs = sorted(docs, key=lambda d: d.score, reverse=True)
        top_docs = sorted_docs[: params.top_k]

        for idx, doc in enumerate(top_docs):
            doc.rank = idx + 1

        step_logger.emit_step(
            step=StepType.RERANK,
            data={
                "top_k": params.top_k,
                "total_input": len(docs),
                "selected": [
                    {"rank": d.rank, "score": d.score, "title": d.title, "url": d.url}
                    for d in top_docs
                ],
            },
            attempt=attempt,
        )
        logger.info(
            "[%s] rank: %d → top %d selected",
            self.source.value, len(docs), len(top_docs),
        )
        return top_docs
