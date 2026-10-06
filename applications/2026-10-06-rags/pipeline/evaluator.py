# pipeline/evaluator.py
"""独立 Evaluator。

取得文書の十分性を LLM で判定し、不十分な場合は不足情報を返す。
"""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from pipeline.models import PipelineParams, RetrievedDoc, SourceType, StepType
from pipeline.step_logger import StepLogger

logger = logging.getLogger(__name__)

_EVAL_SYSTEM = """あなたは RAG システムの検索品質を評価する専門家です。
ユーザーの質問に対して取得された文書が、質問に十分答えられるかを判定してください。

判定基準:
- sufficient（十分）: 取得文書から質問に対する明確な回答が導ける
- insufficient（不十分）: 重要な情報が欠けており、質問に答えられない可能性が高い

出力形式（JSON のみ、説明不要）:
{{"verdict": "sufficient" | "insufficient", "confidence": 0.0-1.0, "missing_info": "不足している情報の説明（insufficientの場合）", "reason": "判定理由"}}"""

_EVAL_HUMAN = """質問: {question}

取得文書（上位{count}件）:
{docs_text}

上記の文書で質問に十分答えられますか？"""


class Evaluator:
    """取得文書の十分性を独立評価する。

    Attributes:
        source: ソース種別。
        _llm: LangChain LLM インスタンス。
    """

    def __init__(self, source: SourceType, openai_api_key: str, model: str = "gpt-4o") -> None:
        """初期化。

        Args:
            source: ソース種別。
            openai_api_key: OpenAI APIキー。
            model: 使用するモデル名。
        """
        self.source = source
        self._llm = ChatOpenAI(model=model, temperature=0, api_key=openai_api_key)

    async def evaluate(
        self,
        docs: list[RetrievedDoc],
        params: PipelineParams,
        step_logger: StepLogger,
        attempt: int = 1,
    ) -> tuple[bool, str, str]:
        """取得文書が十分かを評価する。

        Args:
            docs: 検索結果文書リスト。
            params: パイプラインパラメータ。
            step_logger: ステップロガー。
            attempt: 試行回数。

        Returns:
            (is_sufficient, missing_info, reason) のタプル。
        """
        import json

        if not docs:
            step_logger.emit_step(
                step=StepType.EVALUATE,
                data={"verdict": "insufficient", "reason": "取得文書が0件", "confidence": 0.0},
                attempt=attempt,
            )
            return False, "検索結果が0件でした", "文書なし"

        docs_text = "\n\n".join(
            f"[{d.rank}] {d.title} (score: {d.score:.3f})\n{d.content[:300]}..."
            for d in docs
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", _EVAL_SYSTEM),
            ("human", _EVAL_HUMAN),
        ])
        chain = prompt | self._llm
        response = await chain.ainvoke({
            "question": params.question,
            "count": len(docs),
            "docs_text": docs_text,
        })

        raw = response.content.strip()
        try:
            clean = raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean)
        except json.JSONDecodeError:
            logger.warning("[%s] evaluator: JSON parse failed", self.source.value)
            result = {"verdict": "sufficient", "confidence": 0.5, "missing_info": "", "reason": raw}

        is_sufficient = result.get("verdict", "sufficient") == "sufficient"
        missing_info = result.get("missing_info", "")
        reason = result.get("reason", "")
        confidence = result.get("confidence", 0.0)

        step_logger.emit_step(
            step=StepType.EVALUATE,
            data={
                "verdict": result.get("verdict"),
                "confidence": confidence,
                "missing_info": missing_info,
                "reason": reason,
                "doc_count": len(docs),
            },
            attempt=attempt,
        )
        logger.info(
            "[%s] evaluate attempt=%d: %s (conf=%.2f)",
            self.source.value, attempt, result.get("verdict"), confidence,
        )
        return is_sufficient, missing_info, reason
