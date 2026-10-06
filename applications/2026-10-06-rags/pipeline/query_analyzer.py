# pipeline/query_analyzer.py
"""ソース別 QueryAnalyzer。

各ソースの検索特性に合わせてクエリを生成する。
"""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from pipeline.models import PipelineParams, SourceType, StepType
from pipeline.step_logger import StepLogger

logger = logging.getLogger(__name__)

# --- ソース別システムプロンプト ---

_POSTGRES_SYSTEM = """あなたは PostgreSQL の全文検索・ベクター検索に最適化された検索クエリを生成する専門家です。
ユーザーの質問から、以下を出力してください：
- keywords: 英単語・日本語キーワードのスペース区切りリスト（5〜10語）
- section_hint: 関連するドキュメントセクション名のヒント（任意）
- lang_filter: "ja", "en", "ja+en" のいずれか

出力形式（JSON のみ、説明不要）:
{{"keywords": "...", "section_hint": "...", "lang_filter": "..."}}"""

_MYSQL_SYSTEM = """あなたは MySQL FULLTEXT BOOLEAN MODE 検索に最適化されたクエリを生成する専門家です。
ユーザーの質問から、BOOLEAN MODE で使える検索クエリを生成してください。
- 必須キーワードには + を付ける（例: +DynamoDB +GSI）
- 重要フレーズはダブルクォートで囲む（例: +"global secondary index"）
- 除外したいキーワードには - を付ける（任意）

出力形式（JSON のみ、説明不要）:
{{"boolean_query": "...", "keywords_plain": "..."}}"""

_QDRANT_SYSTEM = """あなたはベクター埋め込み検索に最適化されたクエリ文を生成する専門家です。
ユーザーの質問を、意味的に豊かで検索精度が高まるように言い換えてください。
- キーワードの羅列ではなく、自然な文章で記述する
- 日本語・英語どちらでも可（質問の言語に合わせる）
- 同義語や関連概念を含めて表現を広げる

出力形式（JSON のみ、説明不要）:
{{"query_text": "...", "expanded_query": "..."}}"""

_WEB_SYSTEM = """あなたは検索エンジン向けの検索クエリを生成する専門家です。
ユーザーの質問から、Google 等の検索エンジンで最良の結果が得られる検索クエリを生成してください。
- 具体的な技術用語・製品名を含める
- 年号（2024, 2025）を適宜付ける
- AWS公式ドキュメントが返ってきやすいよう "site:docs.aws.amazon.com" は必要に応じて追加
- 英語クエリも生成する（日本語と両方）

出力形式（JSON のみ、説明不要）:
{{"query_ja": "...", "query_en": "...", "site_restricted": false}}"""

_RETRY_SUFFIX = """
前回の検索では十分な情報が得られませんでした。
前回のキーワード: {previous_keywords}
不足している情報: {missing_info}
より広い・別の視点でクエリを生成してください。"""

_SOURCE_SYSTEMS: dict[SourceType, str] = {
    SourceType.POSTGRES: _POSTGRES_SYSTEM,
    SourceType.MYSQL: _MYSQL_SYSTEM,
    SourceType.QDRANT: _QDRANT_SYSTEM,
    SourceType.WEB: _WEB_SYSTEM,
}


class QueryAnalyzer:
    """ソース別に最適化されたクエリを生成する。

    Attributes:
        source: ソース種別。
        _llm: LangChain LLM インスタンス。
    """

    def __init__(
        self,
        source: SourceType,
        openai_api_key: str,
        model: str = "gpt-4o",
    ) -> None:
        """初期化。

        Args:
            source: ソース種別。
            openai_api_key: OpenAI APIキー。
            model: 使用するモデル名。
        """
        self.source = source
        self._llm = ChatOpenAI(
            model=model,
            temperature=0,
            api_key=openai_api_key,
        )

    def _build_prompt(self, is_retry: bool = False) -> ChatPromptTemplate:
        """プロンプトテンプレートを構築する。

        Args:
            is_retry: 再検索かどうか。

        Returns:
            ChatPromptTemplate インスタンス。
        """
        system = _SOURCE_SYSTEMS[self.source]
        if is_retry:
            system += _RETRY_SUFFIX
        return ChatPromptTemplate.from_messages([
            ("system", system),
            ("human", "{question}"),
        ])

    async def analyze(
        self,
        params: PipelineParams,
        step_logger: StepLogger,
        attempt: int = 1,
        previous_keywords: str = "",
        missing_info: str = "",
    ) -> dict[str, str]:
        """クエリを生成してステップログに記録する。

        Args:
            params: パイプラインパラメータ。
            step_logger: ステップロガー。
            attempt: 試行回数。
            previous_keywords: 前回のキーワード（再検索時）。
            missing_info: 不足情報の説明（再検索時）。

        Returns:
            ソース別のクエリ辞書。
        """
        import json

        is_retry = attempt > 1
        prompt = self._build_prompt(is_retry=is_retry)

        chain = prompt | self._llm
        question = params.question
        if is_retry:
            invoke_input = {
                "question": question,
                "previous_keywords": previous_keywords,
                "missing_info": missing_info,
            }
        else:
            invoke_input = {"question": question}

        response = await chain.ainvoke(invoke_input)
        raw_text = response.content.strip()

        try:
            # コードブロックを除去してパース
            clean = raw_text.replace("```json", "").replace("```", "").strip()
            query_dict = json.loads(clean)
        except json.JSONDecodeError:
            logger.warning("[%s] query_analyzer: JSON parse failed, using raw", self.source.value)
            query_dict = {"raw": raw_text}

        step_logger.emit_step(
            step=StepType.QUERY_ANALYZE,
            data={
                "question": params.question,
                "generated_query": query_dict,
                "attempt": attempt,
            },
            attempt=attempt,
        )
        logger.info("[%s] query_analyze attempt=%d: %s", self.source.value, attempt, query_dict)
        return query_dict
