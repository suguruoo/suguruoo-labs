# api/main.py
"""FastAPI アプリケーション。

POST /query        → SSE ストリームで全ステップログと最終結果を返す。
GET  /results      → 保存済み実行結果の一覧を返す。
GET  /results/{id} → 特定の実行結果を返す。
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
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

_RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "results")
os.makedirs(_RESULTS_DIR, exist_ok=True)

app = FastAPI(title="DynamoDB RAG PoC API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _format_sse(event: SSEEvent) -> str:
    return f"data: {json.dumps(event.model_dump(), ensure_ascii=False)}\n\n"


def _save_result(result_id: str, params: PipelineParams, results: dict) -> None:
    payload = {
        "id": result_id,
        "timestamp": datetime.now().isoformat(),
        "params": params.model_dump(),
        "results": {
            src: {
                "source": r.source.value,
                "final_answer": r.final_answer,
                "retry_count": r.retry_count,
                "total_sec": r.total_sec,
                "query_analyze_sec": r.query_analyze_sec,
                "retrieve_sec": r.retrieve_sec,
                "evaluate_sec": r.evaluate_sec,
                "generate_sec": r.generate_sec,
                "hit_count": r.hit_count,
                "total_input_tokens": r.total_input_tokens,
                "total_output_tokens": r.total_output_tokens,
                "top_docs": [d.model_dump() for d in r.top_docs],
            }
            for src, r in results.items() if isinstance(r, PipelineResult)
        },
    }
    with open(os.path.join(_RESULTS_DIR, f"{result_id}.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


async def _pipeline_stream(params: PipelineParams, result_id: str):
    final_results: dict = {}
    try:
        async for item in run_parallel_pipelines(params):
            if isinstance(item, StepLog):
                yield _format_sse(SSEEvent(
                    event_type="step", source=item.source.value,
                    data={"step": item.step.value, "attempt": item.attempt,
                          "elapsed_sec": item.elapsed_sec, **item.data},
                ))
            elif isinstance(item, dict):
                final_results = item
                results_data = {}
                for src, r in item.items():
                    if isinstance(r, PipelineResult):
                        results_data[src] = {
                            "final_answer": r.final_answer,
                            "retry_count": r.retry_count,
                            "top_docs": [d.model_dump() for d in r.top_docs],
                            "total_sec": r.total_sec,
                            "query_analyze_sec": r.query_analyze_sec,
                            "retrieve_sec": r.retrieve_sec,
                            "evaluate_sec": r.evaluate_sec,
                            "generate_sec": r.generate_sec,
                            "hit_count": r.hit_count,
                            "total_input_tokens": r.total_input_tokens,
                            "total_output_tokens": r.total_output_tokens,
                        }
                yield _format_sse(SSEEvent(event_type="result", source="all", data=results_data))

        yield _format_sse(SSEEvent(event_type="done", source="all", data={"result_id": result_id}))
        _save_result(result_id, params, final_results)

    except Exception as exc:
        logger.error("pipeline stream error: %s", exc)
        yield _format_sse(SSEEvent(event_type="error", source="all", data={"error": str(exc)}))


@app.post("/query")
async def query(request: QueryRequest) -> StreamingResponse:
    result_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    params = PipelineParams(**request.model_dump())
    return StreamingResponse(
        _pipeline_stream(params, result_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/results")
async def list_results() -> list[dict]:
    files = sorted([f for f in os.listdir(_RESULTS_DIR) if f.endswith(".json")], reverse=True)
    out = []
    for fname in files[:50]:
        try:
            with open(os.path.join(_RESULTS_DIR, fname), encoding="utf-8") as f:
                d = json.load(f)
            out.append({
                "id": d["id"], "timestamp": d["timestamp"],
                "question": d["params"]["question"],
                "model": d["params"]["model"],
                "top_k": d["params"]["top_k"],
                "language": d["params"]["language"],
                "sources": list(d["results"].keys()),
            })
        except Exception:
            continue
    return out


@app.get("/results/{result_id}")
async def get_result(result_id: str) -> dict:
    path = os.path.join(_RESULTS_DIR, f"{result_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Result not found")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.patch("/results/{result_id}/comment")
async def update_comment(result_id: str, body: dict) -> dict:
    """指定ソースへのコメントを JSON に保存する。

    body: {"source": "postgres", "comment": "..."}
    """
    path = os.path.join(_RESULTS_DIR, f"{result_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Result not found")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "comments" not in data:
        data["comments"] = {}
    data["comments"][body["source"]] = body.get("comment", "")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"ok": True, "source": body["source"], "comment": body.get("comment", "")}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

