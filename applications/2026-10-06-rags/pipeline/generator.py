# pipeline/generator.py
"""独立 Generator。

Top-K 文書を使って新規セッションで最終回答を生成する。
"""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from pipeline.models import PipelineParams, RetrievedDoc, SourceType, StepType
from pipeline.step_logger import StepLogger

logger = logging.getLogger(__name__)

_GENERATE_SYSTEM = """あなたは AWS DynamoDB の専門家です。
提供されたドキュメントのみを根拠として、ユーザーの質問に日本語で正確に回答してください。

回答ルール:
- ドキュメントに記載のない情報は推測で補わない
- 根拠となる箇所を「[出典: タイトル]」形式で明示する
- 箇条書きや見出しを使って読みやすく整形する
- 情報が不十分な場合はその旨を明記する

データソース: {source_name}"""

_GENERATE_HUMAN = """質問: {question}

参考ドキュメント（Top-{count}件）:
{docs_text}

上記のドキュメントをもとに質問に回答してください。"""

_SOURCE_NAMES: dict[SourceType, str] = {
    SourceType.POSTGRES: "PostgreSQL Document DB (pgvector)",
    SourceType.MYSQL: "MySQL RDB Index (FULLTEXT)",
    SourceType.QDRANT: "Qdrant Vector DB (cosine similarity)",
    SourceType.WEB: "Natural Web Fetch (OpenAI web_search)",
}


class Generator:
    """Top-K 文書から独立した最終回答を生成する。

    Attributes:
        source: ソース種別。
        _openai_api_key: OpenAI APIキー。
    """

    def __init__(self, source: SourceType, openai_api_key: str) -> None:
        """初期化。

        Args:
            source: ソース種別。
            openai_api_key: OpenAI APIキー。
        """
        self.source = source
        self._openai_api_key = openai_api_key

    async def generate(
        self,
        top_docs: list[RetrievedDoc],
        params: PipelineParams,
        step_logger: StepLogger,
        attempt: int = 1,
    ) -> str:
        """Top-K 文書から最終回答を生成する。新規セッションで実行する。

        Args:
            top_docs: Top-K 文書リスト。
            params: パイプラインパラメータ。
            step_logger: ステップロガー。
            attempt: 最終試行回数。

        Returns:
            最終回答文字列。
        """
        # 新規セッション: 毎回新しい LLM インスタンスを生成（セッション独立）
        llm = ChatOpenAI(
            model=params.model,
            temperature=params.temperature,
            top_p=params.top_p,
            api_key=self._openai_api_key,
        )

        docs_text = "\n\n".join(
            f"[{d.rank}] {d.title}\nURL: {d.url}\n{d.content}"
            for d in top_docs
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", _GENERATE_SYSTEM),
            ("human", _GENERATE_HUMAN),
        ])
        chain = prompt | llm

        response = await chain.ainvoke({
            "source_name": _SOURCE_NAMES[self.source],
            "question": params.question,
            "count": len(top_docs),
            "docs_text": docs_text,
        })

        answer = response.content.strip()

        step_logger.emit_step(
            step=StepType.GENERATE,
            data={
                "answer": answer,
                "source": self.source.value,
                "model": params.model,
                "top_k_used": len(top_docs),
            },
            attempt=attempt,
        )
        logger.info("[%s] generate done: %d chars", self.source.value, len(answer))
        return answer
