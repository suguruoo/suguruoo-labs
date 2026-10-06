# api/models.py
"""API リクエスト / レスポンス Pydantic スキーマ。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """POST /query リクエストボディ。"""

    question: str = Field(..., min_length=1, description="ユーザーの質問")
    model: str = Field(default="gpt-4o")
    top_k: int = Field(default=5, ge=1, le=20)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    reasoning: bool = Field(default=True)
    embedding_model: str = Field(default="text-embedding-3-small")
    language: Literal["ja", "en", "ja+en"] = Field(default="ja+en")
    max_retry: int = Field(default=3, ge=1, le=5)


class SSEEvent(BaseModel):
    """SSE で送信するイベント。"""

    event_type: str  # "step" | "result" | "error" | "done"
    source: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
