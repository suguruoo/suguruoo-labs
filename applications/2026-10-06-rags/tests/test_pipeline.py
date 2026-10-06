# tests/test_pipeline.py
"""パイプライン共通モデルと Ranker のユニットテスト。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline.models import (
    PipelineParams,
    PipelineResult,
    RetrievedDoc,
    SourceType,
    StepLog,
    StepType,
)
from pipeline.ranker import Ranker


class TestPipelineParams:
    def test_default_values(self) -> None:
        params = PipelineParams(question="DynamoDB GSI とは？")
        assert params.top_k == 5
        assert params.temperature == 0.3
        assert params.language == "ja+en"
        assert params.max_retry == 3

    def test_top_k_bounds(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PipelineParams(question="test", top_k=0)
        with pytest.raises(ValidationError):
            PipelineParams(question="test", top_k=21)

    def test_temperature_bounds(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PipelineParams(question="test", temperature=2.1)


class TestRetrievedDoc:
    def test_default_score(self) -> None:
        doc = RetrievedDoc(content="test content")
        assert doc.score == 0.0
        assert doc.rank == 0

    def test_full_doc(self) -> None:
        doc = RetrievedDoc(
            content="DynamoDB の GSI について",
            url="https://docs.aws.amazon.com/",
            title="GSI Guide",
            score=0.95,
            rank=1,
        )
        assert doc.score == 0.95


class TestRanker:
    def _make_docs(self) -> list[RetrievedDoc]:
        return [
            RetrievedDoc(content="doc1", score=0.7, rank=3),
            RetrievedDoc(content="doc2", score=0.95, rank=1),
            RetrievedDoc(content="doc3", score=0.85, rank=2),
            RetrievedDoc(content="doc4", score=0.6, rank=4),
            RetrievedDoc(content="doc5", score=0.5, rank=5),
        ]

    def _make_step_logger(self) -> MagicMock:
        logger = MagicMock()
        logger.emit_step = MagicMock()
        return logger

    def test_rank_returns_top_k(self) -> None:
        ranker = Ranker(source=SourceType.POSTGRES)
        params = PipelineParams(question="test", top_k=3)
        docs = self._make_docs()
        result = ranker.rank(docs=docs, params=params, step_logger=self._make_step_logger())
        assert len(result) == 3

    def test_rank_sorts_by_score_descending(self) -> None:
        ranker = Ranker(source=SourceType.MYSQL)
        params = PipelineParams(question="test", top_k=3)
        docs = self._make_docs()
        result = ranker.rank(docs=docs, params=params, step_logger=self._make_step_logger())
        scores = [d.score for d in result]
        assert scores == sorted(scores, reverse=True)

    def test_rank_reassigns_rank_index(self) -> None:
        ranker = Ranker(source=SourceType.QDRANT)
        params = PipelineParams(question="test", top_k=3)
        docs = self._make_docs()
        result = ranker.rank(docs=docs, params=params, step_logger=self._make_step_logger())
        for expected_rank, doc in enumerate(result, start=1):
            assert doc.rank == expected_rank

    def test_rank_emits_step_log(self) -> None:
        ranker = Ranker(source=SourceType.WEB)
        params = PipelineParams(question="test", top_k=2)
        docs = self._make_docs()
        logger = self._make_step_logger()
        ranker.rank(docs=docs, params=params, step_logger=logger)
        logger.emit_step.assert_called_once()

    def test_rank_empty_docs(self) -> None:
        ranker = Ranker(source=SourceType.POSTGRES)
        params = PipelineParams(question="test", top_k=5)
        result = ranker.rank(docs=[], params=params, step_logger=self._make_step_logger())
        assert result == []


class TestStepLog:
    def test_step_log_creation(self) -> None:
        log = StepLog(
            source=SourceType.POSTGRES,
            step=StepType.QUERY_ANALYZE,
            attempt=1,
            data={"keywords": "GSI index"},
        )
        assert log.source == SourceType.POSTGRES
        assert log.step == StepType.QUERY_ANALYZE
        assert log.data["keywords"] == "GSI index"
