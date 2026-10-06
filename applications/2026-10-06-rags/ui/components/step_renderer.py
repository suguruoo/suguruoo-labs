# ui/components/step_renderer.py
"""ステップ表示コンポーネント。各ステップを Streamlit 要素で描画する。"""

from __future__ import annotations

from typing import Any

import streamlit as st

_STEP_ICONS = {
    "query_analyze": "① 🔍 Query 解析",
    "retrieve_request": "② 📤 検索リクエスト",
    "retrieve_result": "② 📥 検索結果",
    "evaluate": "③ ✅ 十分性評価",
    "rerank": "④ 🏆 Top-K 選定",
    "generate": "⑤ 💬 最終回答",
    "error": "❌ エラー",
}

_STEP_COLORS = {
    "query_analyze": "#1f77b4",
    "retrieve_request": "#ff7f0e",
    "retrieve_result": "#2ca02c",
    "evaluate": "#d62728",
    "rerank": "#9467bd",
    "generate": "#8c564b",
    "error": "#e377c2",
}


def render_step(
    step: str,
    data: dict[str, Any],
    attempt: int,
    container: Any,
) -> None:
    """1ステップを Streamlit コンテナに描画する。

    Args:
        step: ステップ種別文字列。
        data: ステップデータ辞書。
        attempt: 試行回数。
        container: st.container() など描画先コンテナ。
    """
    label = _STEP_ICONS.get(step, f"📌 {step}")
    if attempt > 1:
        label += f" (再試行 {attempt})"

    with container:
        with st.expander(label, expanded=(step == "generate")):
            if step == "query_analyze":
                _render_query_analyze(data)
            elif step == "retrieve_request":
                _render_retrieve_request(data)
            elif step == "retrieve_result":
                _render_retrieve_result(data)
            elif step == "evaluate":
                _render_evaluate(data)
            elif step == "rerank":
                _render_rerank(data)
            elif step == "generate":
                _render_generate(data)
            elif step == "error":
                st.error(data.get("error", "不明なエラー"))
            else:
                st.json(data)


def _render_query_analyze(data: dict[str, Any]) -> None:
    st.caption("生成されたクエリ")
    q = data.get("generated_query", {})
    if isinstance(q, dict):
        st.json(q)
    else:
        st.code(str(q))


def _render_retrieve_request(data: dict[str, Any]) -> None:
    st.caption("検索パラメータ")
    for k, v in data.items():
        if k not in ("top_k",):
            st.text(f"{k}: {v}")
    st.caption(f"Top-K: {data.get('top_k', '-')}")


def _render_retrieve_result(data: dict[str, Any]) -> None:
    count = data.get("count", 0)
    st.caption(f"取得件数: {count}")
    docs = data.get("docs", [])
    if docs:
        for doc in docs:
            score = doc.get("score", 0.0)
            title = doc.get("title") or doc.get("url", "")
            rank = doc.get("rank", "-")
            st.markdown(f"**[{rank}]** `score: {score:.4f}` — {title}")
    else:
        st.warning("取得文書なし")


def _render_evaluate(data: dict[str, Any]) -> None:
    verdict = data.get("verdict", "")
    if "warning" in data:
        st.warning(data["warning"])
        return
    if verdict == "sufficient":
        st.success(f"✅ 十分 (confidence: {data.get('confidence', 0):.2f})")
    elif verdict == "insufficient":
        st.warning(f"⚠️ 不十分 (confidence: {data.get('confidence', 0):.2f})")
        st.caption(f"不足情報: {data.get('missing_info', '')}")
    st.caption(f"理由: {data.get('reason', '')}")


def _render_rerank(data: dict[str, Any]) -> None:
    st.caption(f"Top-{data.get('top_k', '-')} 選定 (入力: {data.get('total_input', '-')} 件)")
    selected = data.get("selected", [])
    for doc in selected:
        st.markdown(
            f"**[{doc.get('rank')}]** `{doc.get('score', 0):.4f}` — {doc.get('title') or doc.get('url', '')}"
        )


def _render_generate(data: dict[str, Any]) -> None:
    answer = data.get("answer", "")
    st.markdown(answer)
    st.caption(
        f"Model: {data.get('model', '-')} | "
        f"Top-K 使用: {data.get('top_k_used', '-')} 件 | "
        f"Source: {data.get('source', '-')}"
    )
