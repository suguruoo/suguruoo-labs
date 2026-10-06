# pipeline/step_logger.py
"""LangChain Callback を使った全ステップログ収集。

asyncio.Queue にログを投入し、SSE ストリームに流す。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

from pipeline.models import SourceType, StepLog, StepType

logger = logging.getLogger(__name__)


class StepLogger(AsyncCallbackHandler):
    """LangChain の各イベントをキャプチャして Queue に投入する Callback。

    Attributes:
        source: このロガーが担当するソース種別。
        queue: ログを流す asyncio.Queue。
    """

    def __init__(self, source: SourceType, queue: asyncio.Queue[StepLog]) -> None:
        """初期化。

        Args:
            source: ソース種別。
            queue: ログ投入先キュー。
        """
        super().__init__()
        self.source = source
        self.queue = queue

    def _put(self, log: StepLog) -> None:
        """キューにログを投入する（同期・非同期どちらからも呼べる）。"""
        try:
            self.queue.put_nowait(log)
        except asyncio.QueueFull:
            logger.warning("step_logger queue full, dropping log: %s", log.step)

    async def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """チェーン開始時。"""
        chain_name = serialized.get("name", "unknown")
        logger.debug("[%s] chain_start: %s", self.source.value, chain_name)

    async def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """LLM 呼び出し開始時。"""
        logger.debug("[%s] llm_start", self.source.value)

    async def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """LLM 呼び出し終了時。"""
        logger.debug("[%s] llm_end", self.source.value)

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """LLM エラー時。"""
        self._put(
            StepLog(
                source=self.source,
                step=StepType.ERROR,
                data={"error": str(error)},
            )
        )

    def emit_step(self, step: StepType, data: dict[str, Any], attempt: int = 1) -> None:
        """外部からステップログを直接投入する。

        Args:
            step: ステップ種別。
            data: ステップデータ。
            attempt: 再試行回数。
        """
        self._put(
            StepLog(
                source=self.source,
                step=step,
                attempt=attempt,
                data=data,
            )
        )
