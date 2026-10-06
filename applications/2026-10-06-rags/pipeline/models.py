# pipeline/models.py
"""パイプライン全体で共有する Pydantic モデル定義。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """RAG ソース種別。"""

    POSTGRES = "postgres"
    MYSQL = "mysql"
    QDRANT = "qdrant"
    WEB = "web"


class StepType(str, Enum):
    """パイプラインステップ種別。"""

    QUERY_ANALYZE = "query_analyze"
    RETRIEVE_REQUEST = "retrieve_request"
    RETRIEVE_RESULT = "retrieve_result"
    EVALUATE = "evaluate"
    RERANK = "rerank"
    GENERATE = "generate"
    ERROR = "error"


class RetrievedDoc(BaseModel):
    """検索で取得された1文書。"""

    content: str
    url: str = ""
    title: str = ""
    section: str = ""
    lang: str = ""
    score: float = 0.0
    rank: int = 0


class StepLog(BaseModel):
    """1ステップのログエントリ。SSE で送信する単位。"""

    source: SourceType
    step: StepType
    attempt: int = 1  # 再検索ループの何回目か
    data: dict[str, Any] = Field(default_factory=dict)
    # data の中身はステップごとに異なる


class PipelineParams(BaseModel):
    """フロントエンドから受け取る RAG パラメータ。"""

    question: str
    model: str = "gpt-4o"
    top_k: int = Field(default=5, ge=1, le=20)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    reasoning: bool = True
    embedding_model: str = "text-embedding-3-small"
    language: Literal["ja", "en", "ja+en"] = "ja+en"
    max_retry: int = Field(default=3, ge=1, le=5)


class PipelineResult(BaseModel):
    """1本のパイプラインの最終出力。"""

    source: SourceType
    final_answer: str
    top_docs: list[RetrievedDoc] = Field(default_factory=list)
    retry_count: int = 0
    steps: list[StepLog] = Field(default_factory=list)
