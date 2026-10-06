# api/main.py
"""FastAPI アプリケーション。

POST /query → SSE ストリームで全ステップログと最終結果を返す。
"""

from __future__ import annotations

import json
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# .env / .secrets を起動時に読み込む
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(_env_path)
_secrets_path = os.path.join(os.path.dirname(__file__), "..", ".secrets")
if os.path.exists(_secrets_path):
    with open(_secrets_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if "=" in _line and not _line.startswith("#"):
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip().strip('"'), _v.strip().strip('"'))

from api.models import QueryRequest, SSEEvent
from pipeline.models import PipelineParams, PipelineResult, StepLog
from pipeline.rag_chain import run_parallel_pipelines

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="DynamoDB RAG PoC API",
    version="0.1.0",
    description="4本独立 RAG パイプライン比較 API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _format_sse(event: SSEEvent) -> str:
    """SSEEvent を SSE フォーマット文字列に変換する。

    Args:
        event: SSEEvent インスタンス。

    Returns:
        "data: {...}\n\n" 形式の文字列。
    """
    payload = json.dumps(event.model_dump(), ensure_ascii=False)
    return f"data: {payload}\n\n"


async def _pipeline_stream(params: PipelineParams):
    """パイプラインを実行して SSE イベントを yield する非同期ジェネレーター。

    Args:
        params: パイプラインパラメータ。

    Yields:
        SSE フォーマット文字列。
    """
    try:
        async for item in run_parallel_pipelines(params):
            if isinstance(item, StepLog):
                event = SSEEvent(
                    event_type="step",
                    source=item.source.value,
                    data={
                        "step": item.step.value,
                        "attempt": item.attempt,
                        **item.data,
                    },
                )
                yield _format_sse(event)

            elif isinstance(item, dict):
                # 最終結果マップ
                results_data: dict[str, dict] = {}
                for src, result in item.items():
                    if isinstance(result, PipelineResult):
                        results_data[src] = {
                            "final_answer": result.final_answer,
                            "retry_count": result.retry_count,
                            "top_docs": [d.model_dump() for d in result.top_docs],
                        }
                event = SSEEvent(
                    event_type="result",
                    source="all",
                    data=results_data,
                )
                yield _format_sse(event)

        yield _format_sse(SSEEvent(event_type="done", source="all", data={}))

    except Exception as exc:
        logger.error("pipeline stream error: %s", exc)
        yield _format_sse(
            SSEEvent(event_type="error", source="all", data={"error": str(exc)})
        )


@app.post("/query")
async def query(request: QueryRequest) -> StreamingResponse:
    """4本パイプラインを並列実行し SSE で結果をストリーミングする。

    Args:
        request: クエリリクエスト。

    Returns:
        SSE StreamingResponse。
    """
    params = PipelineParams(
        question=request.question,
        model=request.model,
        top_k=request.top_k,
        top_p=request.top_p,
        temperature=request.temperature,
        reasoning=request.reasoning,
        embedding_model=request.embedding_model,
        language=request.language,
        max_retry=request.max_retry,
    )
    return StreamingResponse(
        _pipeline_stream(params),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """ヘルスチェックエンドポイント。"""
    return {"status": "ok"}
