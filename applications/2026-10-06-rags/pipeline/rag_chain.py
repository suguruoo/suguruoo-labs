# pipeline/rag_chain.py
"""4本独立 RAG パイプラインのオーケストレーター。

各パイプラインは QueryAnalyzer → Retriever → Evaluator(loop) → Ranker → Generator
の順で独立実行。asyncio で4本を並列起動する。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, AsyncGenerator

from pipeline.evaluator import Evaluator
from pipeline.generator import Generator
from pipeline.models import (
    PipelineParams,
    PipelineResult,
    RetrievedDoc,
    SourceType,
    StepLog,
    StepType,
)
from pipeline.query_analyzer import QueryAnalyzer
from pipeline.ranker import Ranker
from pipeline.retrievers.mysql_retriever import MySQLRetriever
from pipeline.retrievers.postgres_retriever import PostgresRetriever
from pipeline.retrievers.qdrant_retriever import QdrantRetriever
from pipeline.retrievers.web_retriever import WebRetriever
from pipeline.step_logger import StepLogger

logger = logging.getLogger(__name__)


def _load_settings() -> dict[str, Any]:
    """環境変数から DB 接続設定を読み込む。"""
    secrets_path = os.path.join(os.path.dirname(__file__), "..", ".secrets")
    if os.path.exists(secrets_path):
        with open(secrets_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip().strip('"'), val.strip().strip('"'))

    openai_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_SECRET_KEY", "")
    return {  # noqa: RET504
        "openai_api_key": openai_key,
        "pg": {
            "host": os.environ.get("POSTGRES_HOST", "localhost"),
            "port": int(os.environ.get("POSTGRES_PORT", "5432")),
            "user": os.environ.get("POSTGRES_USER", "raguser"),
            "password": os.environ.get("POSTGRES_PASSWORD", "ragpass"),
            "dbname": os.environ.get("POSTGRES_DB", "ragdb"),
        },
        "mysql": {
            "host": os.environ.get("MYSQL_HOST", "localhost"),
            "port": int(os.environ.get("MYSQL_PORT", "3306")),
            "user": os.environ.get("MYSQL_USER", "raguser"),
            "password": os.environ.get("MYSQL_PASSWORD", "ragpass"),
            "database": os.environ.get("MYSQL_DB", "ragdb"),
        },
        "qdrant": {
            "host": os.environ.get("QDRANT_HOST", "localhost"),
            "port": int(os.environ.get("QDRANT_PORT", "6333")),
            "collection_name": os.environ.get("QDRANT_COLLECTION", "dynamodb_docs"),
        },
    }


async def _run_single_pipeline(
    source: SourceType,
    params: PipelineParams,
    settings: dict[str, Any],
    log_queue: asyncio.Queue[StepLog],
) -> PipelineResult:
    """1本のパイプラインを実行する。

    フロー: QueryAnalyze → Retrieve → Evaluate → (再検索 max retry) → Rank → Generate

    Args:
        source: ソース種別。
        params: パイプラインパラメータ。
        settings: DB接続設定。
        log_queue: ログ投入先キュー。

    Returns:
        PipelineResult。
    """
    openai_key = settings["openai_api_key"]
    step_logger = StepLogger(source=source, queue=log_queue)

    analyzer = QueryAnalyzer(source=source, openai_api_key=openai_key, model=params.model)
    evaluator = Evaluator(source=source, openai_api_key=openai_key, model=params.model)
    ranker = Ranker(source=source)
    generator = Generator(source=source, openai_api_key=openai_key)

    if source == SourceType.POSTGRES:
        retriever: Any = PostgresRetriever(settings["pg"], openai_key)
    elif source == SourceType.MYSQL:
        retriever = MySQLRetriever(settings["mysql"])
    elif source == SourceType.QDRANT:
        retriever = QdrantRetriever(
            host=settings["qdrant"]["host"],
            port=settings["qdrant"]["port"],
            collection_name=settings["qdrant"]["collection_name"],
            openai_api_key=openai_key,
        )
    else:
        retriever = WebRetriever(openai_key)

    docs: list[RetrievedDoc] = []
    previous_keywords = ""
    missing_info = ""
    final_attempt = 1

    for attempt in range(1, params.max_retry + 1):
        final_attempt = attempt

        query_dict = await analyzer.analyze(
            params=params,
            step_logger=step_logger,
            attempt=attempt,
            previous_keywords=previous_keywords,
            missing_info=missing_info,
        )
        docs = await retriever.retrieve(
            query_dict=query_dict,
            params=params,
            step_logger=step_logger,
            attempt=attempt,
        )
        is_sufficient, missing_info, _reason = await evaluator.evaluate(
            docs=docs,
            params=params,
            step_logger=step_logger,
            attempt=attempt,
        )

        if is_sufficient:
            break

        if attempt == params.max_retry:
            step_logger.emit_step(
                step=StepType.EVALUATE,
                data={"warning": f"最大再試行回数({params.max_retry})に達しました。最善の結果で続行します。"},
                attempt=attempt,
            )
            break

        previous_keywords = str(query_dict)

    top_docs = ranker.rank(docs=docs, params=params, step_logger=step_logger, attempt=final_attempt)
    final_answer = await generator.generate(
        top_docs=top_docs,
        params=params,
        step_logger=step_logger,
        attempt=final_attempt,
    )

    return PipelineResult(
        source=source,
        final_answer=final_answer,
        top_docs=top_docs,
        retry_count=final_attempt - 1,
    )


async def run_parallel_pipelines(
    params: PipelineParams,
) -> AsyncGenerator[StepLog | dict[str, PipelineResult], None]:
    """4本のパイプラインを並列実行し、ステップログと最終結果を yield する。

    Args:
        params: パイプラインパラメータ。

    Yields:
        StepLog（各ステップのリアルタイムログ）。
        最後に dict[str, PipelineResult]（全完了後の最終結果マップ）を yield。
    """
    settings = _load_settings()
    log_queue: asyncio.Queue[StepLog] = asyncio.Queue(maxsize=500)
    sources = [SourceType.POSTGRES, SourceType.MYSQL, SourceType.QDRANT, SourceType.WEB]

    tasks = [
        asyncio.create_task(_run_single_pipeline(source, params, settings, log_queue))
        for source in sources
    ]

    _SENTINEL = object()

    async def _drain() -> None:
        await asyncio.gather(*tasks, return_exceptions=True)
        await log_queue.put(_SENTINEL)  # type: ignore[arg-type]

    asyncio.create_task(_drain())

    while True:
        item = await log_queue.get()
        if item is _SENTINEL:
            break
        yield item  # type: ignore[misc]

    results: dict[str, PipelineResult] = {}
    for task, source in zip(tasks, sources):
        try:
            results[source.value] = task.result()
        except Exception as exc:
            logger.error("[%s] pipeline failed: %s", source.value, exc)
            results[source.value] = PipelineResult(
                source=source,
                final_answer=f"エラーが発生しました: {exc}",
                retry_count=0,
            )

    yield results  # type: ignore[misc]

