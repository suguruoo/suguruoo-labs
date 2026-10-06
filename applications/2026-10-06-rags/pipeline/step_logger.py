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
        total_input_tokens: このパイプラインの入力トークン累計。
        total_output_tokens: このパイプラインの出力トークン累計。
    """

    def __init__(self, source: SourceType, queue: asyncio.Queue[StepLog]) -> None:
        super().__init__()
        self.source = source
        self.queue = queue
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0

    def _put(self, log: StepLog) -> None:
        try:
            self.queue.put_nowait(log)
        except asyncio.QueueFull:
            logger.warning("step_logger queue full, dropping log: %s", log.step)

    async def on_chain_start(self, serialized: dict[str, Any], inputs: dict[str, Any],
                             *, run_id: UUID, **kwargs: Any) -> None:
        logger.debug("[%s] chain_start: %s", self.source.value, serialized.get("name", ""))

    async def on_llm_start(self, serialized: dict[str, Any], prompts: list[str],
                           *, run_id: UUID, **kwargs: Any) -> None:
        logger.debug("[%s] llm_start", self.source.value)

    async def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        """LLM 呼び出し終了時にトークン使用量を集計する。"""
        try:
            usage = response.llm_output.get("token_usage", {}) if response.llm_output else {}
            self.total_input_tokens  += usage.get("prompt_tokens", 0)
            self.total_output_tokens += usage.get("completion_tokens", 0)
        except Exception:
            pass
        logger.debug("[%s] llm_end in=%d out=%d",
                     self.source.value, self.total_input_tokens, self.total_output_tokens)

    async def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._put(StepLog(source=self.source, step=StepType.ERROR, data={"error": str(error)}))

    def emit_step(self, step: StepType, data: dict[str, Any], attempt: int = 1) -> None:
        self._put(StepLog(source=self.source, step=step, attempt=attempt, data=data))
